#!/usr/local/bin/python3
# encoding: utf-8

import io
import gzip
import ssl
import socket
import http.client
import urllib.request

def create_connection(address, timeout=None, source_address=None):
    host, port = address
    for addrinfo in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
        addrfamily, socktype, proto, canonname, sockaddr = addrinfo
        sock = None
        try:
            sock = socket.socket(addrfamily, socktype, proto)
            if timeout:
                sock.settimeout(float(timeout))
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except socket.error as e:
            if sock is not None:
                sock.close()
            raise e
    raise socket.error("getaddrinfo returns an empty list")

class SpeedtestHTTPConnection(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        source_address = kwargs.pop('source_address', None)
        timeout = kwargs.pop('timeout', 10)
        self._tunnel_host = None
        HTTPConnection.__init__(self, *args, **kwargs)
        self.source_address = source_address
        self.timeout = timeout

    def connect(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), self.timeout, self.source_address)
        except (AttributeError, TypeError):
            self.sock = create_connection((self.host, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self._tunnel()

        try:
            kwargs = {}
            if hasattr(ssl, 'SSLContext'):
                if self._tunnel_host:
                    kwargs['server_hostname'] = self._tunnel_host
                else:
                    kwargs['server_hostname'] = self.host
            self.sock = self._context.wrap_socket(self.sock, **kwargs)
        except AttributeError:
            self.sock = ssl.wrap_socket(self.sock)
            try:
                self.sock.server_hostname = self.host
            except AttributeError:
                pass

class SpeedtestHTTPSConnection(http.client.HTTPSConnection):
    default_port = 443

    def __init__(self, *args, **kwargs):
        source_address = kwargs.pop('source_address', None)
        timeout = kwargs.pop('timeout', 10)
        self._tunnel_host = None
        HTTPSConnection.__init__(self, *args, **kwargs)
        self.timeout = timeout
        self.source_address = source_address

    def connect(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), self.timeout, self.source_address)
        except (AttributeError, TypeError):
            self.sock = create_connection((self.host, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self._tunnel()

def _build_connection(connection, source_address, timeout, context=None):
    def inner(host, **kwargs):
        kwargs.update({
            'source_address': source_address,
            'timeout': timeout})
        if context:
            kwargs['context'] = context
        return connection(host, **kwargs)
    return inner

class SpeedtestHTTPHandler(urllib.request.AbstractHTTPHandler):
    def __init__(self, debuglevel=0, source_address=None, timeout=10):
        AbstractHTTPHandler.__init__(self, debuglevel)
        self.source_address = source_address
        self.timeout = timeout

    def http_open(self, req):
        return self.do_open(_build_connection(SpeedtestHTTPConnection, self.source_address, self.timeout), req)

    http_request = AbstractHTTPHandler.do_request_

class SpeedtestHTTPSHandler(urllib.request.AbstractHTTPHandler):
    def __init__(self, debuglevel=0, context=None, source_address=None, timeout=10):
        AbstractHTTPHandler.__init__(self, debuglevel)
        self._context = context
        self.source_address = source_address
        self.timeout = timeout

    def https_open(self, req):
        return self.do_open(_build_connection(SpeedtestHTTPSConnection, self.source_address, self.timeout, context=self._context), req)

    https_request = AbstractHTTPHandler.do_request_

def build_opener(handlers=[], source_address=None, timeout=10):
    if source_address:
        source_address = (source_address, 0)

    handlers += [
        ProxyHandler(),
        SpeedtestHTTPHandler(source_address=source_address, timeout=timeout),
        SpeedtestHTTPSHandler(source_address=source_address, timeout=timeout),
        HTTPDefaultErrorHandler(),
        HTTPRedirectHandler(),
        HTTPErrorProcessor(),
    ]

    opener = OpenerDirector()
    for handler in handlers:
        opener.add_handler(handler)
    return opener

class GzipDecodedResponse(gzip.GzipFile):
    def __init__(self, response):
        self.io = io.BytesIO()
        while True:
            chunk = response.read(1024)
            if len(chunk) == 0:
                break
            self.io.write(chunk)
        self.io.seek(0)
        gzip.GzipFile.__init__(self, mode='rb', fileobj=self.io)

    def close(self):
        try:
            gzip.GzipFile.close(self)
        finally:
            self.io.close()

    
def main():
    pass

if __name__ == '__main__':
    main()