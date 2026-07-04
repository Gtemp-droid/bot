import asyncio, socket, threading, logging, pydivert, re

REAL_IP = "57.129.113.60"
AUTH_PORT = 5489
GAME_PORT = 5557
PROXY_AUTH = 5489
PROXY_GAME = 5555
OUTBOUND_SRC = 61234

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
log = logging.getLogger()

def winedivert():
    flt = (
        f"(ip.DstAddr == {REAL_IP} and (tcp.DstPort == {AUTH_PORT} or tcp.DstPort == {GAME_PORT}) and tcp.SrcPort != {OUTBOUND_SRC})"
        f" or (ip.SrcAddr == 127.0.0.1 and (tcp.SrcPort == {PROXY_AUTH} or tcp.SrcPort == {PROXY_GAME}))"
    )
    try:
        with pydivert.WinDivert(flt) as d:
            log.info("[*] WinDivert running")
            for p in d:
                if p.dst_addr == REAL_IP and p.dst_port in (AUTH_PORT, GAME_PORT):
                    if p.dst_port == GAME_PORT:
                        p.dst_port = PROXY_GAME
                    p.dst_addr = "127.0.0.1"
                elif p.src_addr == "127.0.0.1" and p.src_port in (PROXY_AUTH, PROXY_GAME):
                    if p.src_port == PROXY_GAME:
                        p.src_port = GAME_PORT
                    p.src_addr = REAL_IP
                d.send(p)
    except Exception as e:
        log.error(f"[!] WinDivert: {e}")

async def relay(src, dst, tag, cleanup):
    try:
        while True:
            d = await asyncio.wait_for(src.read(65536), 300)
            if not d: break
            dst.write(d); await dst.drain()
            try:
                text = d.decode('latin-1').strip('\x00\n\r ')
                if text: log.info(f"  {tag} {text[:300]}")
            except: pass
    except: pass
    finally: cleanup()

async def handle_auth(r, w):
    pn = w.get_extra_info('peername')
    log.info(f"[+] AUTH {pn}")
    try:
        rs = socket.socket()
        rs.settimeout(10)
        rs.bind(("0.0.0.0", OUTBOUND_SRC))
        rs.connect((REAL_IP, AUTH_PORT))
        rr, rw = await asyncio.open_connection(sock=rs)
        buf = b""
        async def cp(src, dst, tag, cleanup):
            nonlocal buf
            try:
                while True:
                    d = await asyncio.wait_for(src.read(65536), 300)
                    if not d: break
                    if tag == "S>C":
                        buf += d
                        while b"\n" in buf:
                            line, rest = buf.split(b"\n", 1)
                            if b"AYK" in line:
                                m = re.search(br"AY(K\d*)" + re.escape(REAL_IP.encode()) + br":(\d+);(\d+)", line)
                                if m:
                                    old = m.group(0)
                                    new = f"AY{m.group(1).decode()}127.0.0.1:{PROXY_GAME};{m.group(3).decode()}".encode()
                                    line = line.replace(old, new)
                                    log.info(f"  *** Rewrote AYK: {new.decode()}")
                            if line.strip():
                                log.info(f"  S>C {line.decode('latin-1')[:200]}")
                            buf = rest
                        if len(buf) > 4096: buf = b""
                    dst.write(d); await dst.drain()
            except: pass
            finally: cleanup()
        await asyncio.gather(cp(r, rw, "C>S", rw.close), cp(rr, w, "S>C", w.close), return_exceptions=True)
    except Exception as e:
        log.error(f"  AUTH ERR: {e}")
    log.info(f"[-] AUTH {pn}")

async def handle_game(r, w):
    pn = w.get_extra_info('peername')
    log.info(f"[+] GAME {pn}")
    try:
        rs = socket.socket()
        rs.settimeout(10)
        rs.connect((REAL_IP, GAME_PORT))
        rr, rw = await asyncio.open_connection(sock=rs)
        await asyncio.gather(relay(r, rw, "C>S", rw.close), relay(rr, w, "S>C", w.close), return_exceptions=True)
    except Exception as e:
        log.error(f"  GAME ERR: {e}")
    log.info(f"[-] GAME {pn}")

async def main():
    t = threading.Thread(target=winedivert, daemon=True)
    t.start()
    await asyncio.sleep(1)
    if not t.is_alive():
        log.error("WinDivert failed"); return
    srv1 = await asyncio.start_server(handle_auth, "127.0.0.1", PROXY_AUTH)
    srv2 = await asyncio.start_server(handle_game, "127.0.0.1", PROXY_GAME)
    log.info(f"[*] Auth proxy on 127.0.0.1:{PROXY_AUTH}")
    log.info(f"[*] Game proxy on 127.0.0.1:{PROXY_GAME}")
    log.info(f"[*] Forwarding auth to {REAL_IP}:{AUTH_PORT}")
    log.info(f"[*] Forwarding game to {REAL_IP}:{GAME_PORT}")
    await asyncio.gather(srv1.serve_forever(), srv2.serve_forever())

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: log.info("Stopped")
    except Exception as e: log.exception(f"FATAL: {e}")
