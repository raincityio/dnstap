#!/usr/bin/env python3.7

import asyncio
import logging
import ipaddress
import uvloop

class Tapper:

    def __init__(self, callback, host='127.0.0.1', port=8765):
        self.callback = callback
        self.host = host
        self.port = port

    async def loop(self):
        async def process(reader):
            while True:
                domain_sz = int.from_bytes(await reader.readexactly(1), byteorder='big')
                domain = (await reader.readexactly(domain_sz)).decode('utf-8')
                ip_sz = int.from_bytes(await reader.readexactly(1), byteorder='big')
                ip = ipaddress.ip_address(await reader.readexactly(ip_sz))
                try:
                    await self.callback(domain, ip)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logging.error(e)

        while True:
            try:
                writer = None
                reader, writer = await asyncio.open_connection(self.host, self.port)
                await process(reader)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error(e)
            finally:
                if not writer is None:
                    writer.close()
            await asyncio.sleep(1)

async def main():
    async def callback(domain, ip):
        print("%s = %s" % (domain, ip))

    tapper = Tapper(callback)
    await tapper.loop()

if __name__ == '__main__':
    asyncio.run(main())
