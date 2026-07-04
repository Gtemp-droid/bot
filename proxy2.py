import socket, asyncio, logging

REAL_IP = "57.129.113.60"
REAL_PORT = 5557
PROXY_PORT = 5555

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger()

async def handle(r, w):
    peername = w.get_extra_info('peername')
    log.info(f"[+] {peername}")
    try:
        rs = socket.socket()
        rs.settimeout(10)
        rs.connect((REAL_IP, REAL_PORT))
        rr, rw = await asyncio.open_connection(sock=rs)

        async def cp(src, dst, tag, cleanup):
            try:
                while True:
                    d = await asyncio.wait_for(src.read(65536), 300)
                    if not d: break
                    dst.write(d); await dst.drain()
                    try:
                        text = d.decode('latin-1').strip('\x00\n\r ')
                        if text: log.info(f"  {tag} {text[:200]}")
                    except: pass
            except: pass
            finally: cleanup()

        await asyncio.gather(
            cp(r, rw, "C>S", rw.close),
            cp(rr, w, "S>C", w.close),
            return_exceptions=True
        )
    except Exception as e:
        log.error(f"  ERR: {e}")
    log.info(f"[-] {peername}")

async def main():
    srv = await asyncio.start_server(handle, "127.0.0.1", PROXY_PORT)
    log.info(f"[*] Proxy on 127.0.0.1:{PROXY_PORT}")
    log.info(f"[*] Forwarding to {REAL_IP}:{REAL_PORT}")
    await srv.serve_forever()

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: log.info("Stopped")
    except Exception as e: log.exception(f"FATAL: {e}")
