#!/usr/bin/env python3
"""
Dofus 1.29 MITM Proxy - Reborn Retro
Intercepts game traffic, logs/parses packets, forwards bidirectionally.

Requires: Admin privileges, pydivert
"""
import asyncio
import logging
import sys
import os
import subprocess
import socket
import threading
from datetime import datetime

try:
    import pydivert
except ImportError:
    print("pydivert not installed. Install with: pip install pydivert")
    sys.exit(1)

REAL_IP = "57.129.113.60"
REAL_PORT = 5557
PROXY_PORT = 5557
PROXY_OUTBOUND_SRC_PORT = 61234  # Specific port to exclude from WinDivert redirect

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('dofus_proxy.log', mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_game_connection():
    """Find the game client's connection to the real server."""
    try:
        ps_cmd = 'Get-NetTCPConnection -RemoteAddress ' + REAL_IP + ' -RemotePort ' + str(REAL_PORT) + ' -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,@{N=\\"P\\";E={$_.OwningProcess}} | Format-Table -HideTableHeaders -AutoSize'
        result = subprocess.run(["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=5)
        for line in result.stdout.strip().split('\n'):
            parts = line.strip().split()
            if len(parts) >= 3 and parts[0] != '':
                return parts[0], int(parts[1]), parts[2] if len(parts) > 2 else ""
    except Exception as e:
        logger.error(f"Error finding game: {e}")
    return None, None, None


class PacketParser:
    """Parses and logs Dofus 1.29 protocol packets."""
    def __init__(self):
        self.count = 0
        self.state = {
            'map_id': None, 'cell': None, 'x': None, 'y': None,
            'resources': [], 'items': []
        }

    def feed(self, direction, raw_bytes):
        self.count += 1
        try:
            text = raw_bytes.decode('latin-1', errors='replace').strip('\x00\n\r ')
            if not text:
                return
            if '|' in text:
                prefix = text.split('|')[0]
                params = text.split('|')[1:]
            else:
                prefix = text.split('\n')[0] if '\n' in text else text
                params = []

            # Log interesting packets
            if prefix in ('GCK', 'GDM', 'GDF', 'IO', 'Im', 'gDC', 'EA', 'gCK', 'GM', 'GDK'):
                logger.info(f"  {direction} {prefix} {'|'.join(params[:12])}")

            # Track state
            if prefix == 'GCK' and len(params) >= 4:
                self.state['map_id'] = params[0]
                self.state['x'] = params[1]
                self.state['y'] = params[2]
                self.state['cell'] = params[3]
            elif prefix == 'GDM' and len(params) >= 2:
                res = []
                for i in range(0, len(params) - 1, 2):
                    res.append({'cell': params[i], 'type': params[i + 1]})
                self.state['resources'] = res
                logger.info(f"    -> {len(res)} resources on map")
        except Exception as e:
            logger.debug(f"Parse error: {e}")


async def proxy_client(reader, writer, parser):
    """Proxy one TCP connection between game and server."""
    peername = writer.get_extra_info('peername')
    logger.info(f"[+] Connection from {peername}")

    # Connect to real server from a specific source port to avoid WinDivert loops
    out_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    out_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        out_sock.bind(("0.0.0.0", PROXY_OUTBOUND_SRC_PORT))
    except OSError:
        out_sock.bind(("0.0.0.0", 0))

    try:
        out_sock.settimeout(10)
        out_sock.connect((REAL_IP, REAL_PORT))
        r_reader, r_writer = await asyncio.open_connection(sock=out_sock)
    except Exception as e:
        logger.error(f"Can't connect to {REAL_IP}:{REAL_PORT}: {e}")
        writer.close()
        return

    async def relay(src, dst, direction, cleanup):
        buf = b""
        try:
            while True:
                data = await asyncio.wait_for(src.read(65536), timeout=300)
                if not data:
                    break
                dst.write(data)
                await dst.drain()
                # Parse packets line by line
                buf += data
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    if line.strip():
                        parser.feed(direction, line.strip())
                if len(buf) > 1024:
                    parser.feed(direction, buf)
                    buf = b""
        except (asyncio.TimeoutError, ConnectionResetError, ConnectionError, OSError):
            pass
        finally:
            cleanup()

    await asyncio.gather(
        relay(reader, r_writer, "C>S", lambda: r_writer.close()),
        relay(r_reader, writer, "S>C", lambda: writer.close()),
        return_exceptions=True
    )
    logger.info(f"[-] Closed {peername}")


async def start_proxy(parser):
    server = await asyncio.start_server(
        lambda r, w: proxy_client(r, w, parser),
        "127.0.0.1", PROXY_PORT
    )
    logger.info(f"[*] Proxy listening on 127.0.0.1:{PROXY_PORT}")
    async with server:
        await server.serve_forever()


def run_win_divert():
    """WinDivert loop in a separate thread."""
    forward = f"ip.DstAddr == {REAL_IP} and tcp.DstPort == {REAL_PORT} and tcp.SrcPort != {PROXY_OUTBOUND_SRC_PORT}"
    retpath = f"ip.SrcAddr == 127.0.0.1 and tcp.SrcPort == {PROXY_PORT}"
    full_filter = f"({forward}) or ({retpath})"
    logger.info(f"[*] WinDivert filter: {full_filter}")

    try:
        with pydivert.WinDivert(full_filter) as divert:
            logger.info("[*] WinDivert running")
            for packet in divert:
                if packet.dst_addr == REAL_IP and packet.dst_port == REAL_PORT:
                    # Game → Server: redirect to our proxy
                    packet.dst_addr = "127.0.0.1"
                    packet.dst_port = PROXY_PORT
                elif packet.src_addr == "127.0.0.1" and packet.src_port == PROXY_PORT:
                    # Proxy → Game: rewrite src to look like real server
                    packet.src_addr = REAL_IP
                    packet.src_port = REAL_PORT
                divert.send(packet)
    except Exception as e:
        logger.error(f"[!] WinDivert error: {e}")
        logger.error("Make sure you're running as Administrator!")


async def main():
    logger.info("=" * 50)
    logger.info("Dofus 1.29 MITM Proxy")
    logger.info(f"Target: {REAL_IP}:{REAL_PORT}")
    logger.info("=" * 50)

    # Ensure admin
    import ctypes
    if not ctypes.windll.shell32.IsUserAnAdmin():
        logger.error("Must run as Administrator!")
        logger.error("Right-click terminal and 'Run as administrator'")
        return

    # Find game
    game_ip, game_port, proc = get_game_connection()
    if game_port:
        logger.info(f"Game running (PID: {proc}) source port: {game_port}")

    # Start WinDivert
    t = threading.Thread(target=run_win_divert, daemon=True)
    t.start()
    await asyncio.sleep(0.5)

    if not t.is_alive():
        logger.error("WinDivert failed to start. Check admin + driver.")
        return

    # Start proxy
    parser = PacketParser()
    await start_proxy(parser)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[!] Stopped")
    except Exception as e:
        logger.exception(f"[!] Fatal: {e}")
        input("Press Enter to exit...")
