#!/usr/bin/env python3.7

import signal
import asyncio
import logging
import dns.message
import dns.rdatatype
import ipaddress
import sys 

from . import frames
from . import dnstap_pb2

def process_frame(frame):
    dnstap = dnstap_pb2.Dnstap()
    if (not dnstap.type == dnstap_pb2.Dnstap.MESSAGE):
        logging.warn("Unknown dnstap message type: %s" % dnstap.type)
        return
    dnstap.ParseFromString(frame.payload)
    message = dnstap.message
    lookups = []
    if (message.type == dnstap_pb2.Message.CLIENT_RESPONSE):
        m = dns.message.from_wire(message.response_message)
        linker = {}
        for answer in m.answer:
            name = str(answer.name)
            if (not name in linker):
                linker[name] = []
            for item in answer.items:
                linker[name].append(item)
        for question in m.question:
            if (not len(question.items) == 0):
                raise Exception("Unexpected items under question: %s" % question)
            if (not question.rdtype in [dns.rdatatype.A, dns.rdatatype.AAAA]):
                continue
            q = []
            questionname = str(question.name)
            q.append(questionname)
            while (not len(q) == 0):
                name = q.pop()
                if (not name in linker):
                    continue
                for item in linker[name]:
                    itemname = str(item)
                    if (item.rdtype in [dns.rdatatype.A, dns.rdatatype.AAAA]):
                        domain = questionname
                        ip = ipaddress.ip_address(itemname)
                        lookups.append((domain, ip,))
                    elif (item.rdtype in [dns.rdatatype.PTR, dns.rdatatype.CNAME]):
                        q.append(itemname)
                    else:
                        pass
    return lookups

class Spanner:

    def __init__(self, host='0.0.0.0', port=8765):
        self.host = host
        self.port = port
        self.queues = []

    async def add(self, lookups):
        # TODO, i can save some compute
        # if i create the size/encodings up front
        for (domain, ip) in lookups:
            logging.debug("%s = %s" % (domain, ip))
        for queue in self.queues:
            await queue.put(lookups)

    async def start(self):
        async def handle(reader, writer):
            try:
                queue = asyncio.Queue()
                self.queues.append(queue)
                while True:
                    lookups = await queue.get()
                    for (domain, ip) in lookups:
                        domain_sz = len(domain).to_bytes(1, byteorder='big')
                        writer.write(domain_sz)
                        writer.write(domain.encode('utf-8'))
                        ip_sz = len(ip.packed).to_bytes(1, byteorder='big')
                        writer.write(ip_sz)
                        writer.write(ip.packed)
                        await writer.drain()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logging.error(e)
            finally:
                self.queues.remove(queue)
                writer.close()

        await asyncio.start_server(handle, self.host, self.port)

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s]: %(message)s')

    loop = asyncio.get_event_loop()

    finish = asyncio.Event()

    def signal_handler(*args):
        finish.set()
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, signal_handler)
    loop.add_signal_handler(signal.SIGTERM, signal_handler)

    uncaught_exception = None
    def uncaught_handler(loop, context):
        nonlocal uncaught_exception
        if 'exception' in context:
            uncaught_exception = context['exception']
        else:
            uncaught_exception = Exception(context['message'])
        finish.set()
    loop.set_exception_handler(uncaught_handler)

    spanner = Spanner()
    await spanner.start()

    async def frame_callback(frame):
        lookups = process_frame(frame)
        if not len(lookups) == 0:
            await spanner.add(lookups)

    frameStreamServer = frames.UnixFrameStreamServer("/var/run/dnstap.sock", frame_callback)
    await frameStreamServer.start()

    await finish.wait()
    if uncaught_exception is not None:
        raise uncaught_exception
