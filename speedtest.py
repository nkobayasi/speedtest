#!/usr/local/bin/python3
# encoding: utf-8

from functools import wraps
import dataclasses
import re
import random
import io
import os
import os.path
import math
import time
import datetime
import ipaddress
import csv
import json
import hashlib
import platform
import ssl
import queue
import threading
import multiprocessing
import socket
import http.client
import urllib.request
import urllib.parse
import urllib.error
import xml.dom
import xml.dom.minidom
import logging
import logging.handlers

import units

__version__ = '2.1.4b1'

def memoized(func):
    @wraps(func)
    def closure(*args, **kwargs):
        cls = args[0]
        attrname = '_memoized_{0}'.format(func.__name__)
        if not hasattr(cls, attrname):
            setattr(cls, attrname, func(*args, **kwargs))
        return getattr(cls, attrname)
    return closure
cached=memoized

def memoized_property(func):
    return property(memoized(func))
cached_property=memoized_property

def merge_dict(value, other={}):
    value.update(other)
    return value

def create_counter():
    n = 0
    def _counter():
        nonlocal n
        n += 1
        return n
    return _counter
gcounter = create_counter()

def get_anticache_url(url):
    parts = urllib.parse.urlparse(url)
    params = merge_dict(urllib.parse.parse_qs(parts.query), {'x': '%.1f%d' % (time.time() * 1000.0, gcounter(), )})
    return urllib.parse.urlunparse(parts._replace(query=urllib.parse.urlencode(params, doseq=True)))

class StderrHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter('[%(process)d] %(message)s'))

class SyslogHandler(logging.handlers.SysLogHandler):
    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter('%(levelname)s: %(name)s.%(funcName)s(): %(message)s'))

class FileHandler(logging.handlers.WatchedFileHandler):
    def __init__(self, filename):
        super().__init__(filename, encoding='utf-8')
        self.setFormatter(logging.Formatter('[%(asctime)s] [%(process)d] %(levelname)s: %(name)s.%(funcName)s(): %(message)s'))

logger = logging.getLogger('speedtest').getChild(__name__)
logger.addHandler(StderrHandler())

class HttpRetrievalError(Exception): pass

class URL(object):
    def __init__(self, url, secure=True):
        self.url = urllib.parse.urljoin(('http://', 'https://')[bool(secure)], url)
    
    def __repr__(self):
        return '<URL: {}>'.format(self.url)
        
    def __str__(self):
        return self.url
    
    def join(self, path):
        return URL(urllib.parse.urljoin(self.url, path))
    
    @property
    @memoized
    def parse(self):
        return urllib.parse.urlparse(self.url)
    
    @property
    def scheme(self):
        return self.parse.scheme
    
    @property
    def netloc(self):
        return self.parse.netloc
    
    @property
    def hostname(self):
        return self.parse.hostname
    
    @property
    def port(self):
        port_matrix = {
            'http': 80,
            'https': 443, }
        return self.parse.port or port_matrix[self.scheme]
    
    @property
    def path(self):
        path = self.parse.path
        if self.parse.query:
            path += '?' + self.parse.query
        return path
    
    @property
    def value(self):
        return self.url
    
    @property
    def anticache(self):
        return URL(get_anticache_url(self.url))
    
    @property
    @memoized
    def addrinfo(self):
        return socket.getaddrinfo(self.hostname, self.port, proto=socket.IPPROTO_TCP)
    
    def can_resolve4(self):
        return any(map(lambda _: _[0] == socket.AF_INET, self.addrinfo))
    
    def can_resolve6(self):
        return any(map(lambda _: _[0] == socket.AF_INET6, self.addrinfo))
    
    @property
    def addrinfo4(self):
        return list(filter(lambda _: _[0] == socket.AF_INET, self.addrinfo))

    @property
    def addrinfo6(self):
        return list(filter(lambda _: _[0] == socket.AF_INET6, self.addrinfo))
    
    @property
    def resolve4(self):
        if not self.can_resolve4():
            return
        return self.addrinfo4[0][4][0]
    
    @property
    def resolve6(self):
        if not self.can_resolve6():
            return
        return self.addrinfo6[0][4][0]
    
class HttpClient(object):
    @property
    def user_agent(self):
        return (
            'Mozilla/5.0 '
            '({platform}; U; {architecture}; en-us) '
            'Python/{python_version} '
            '(KHTML, like Gecko) '
            'speedtest-cli/{version}').format(
                platform=platform.platform(),
                architecture=platform.architecture()[0],
                python_version=platform.python_version(),
                version=__version__)
        #return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
    
    def get(self, url, params={}, headers={}):
        params.update({'x': '%.1f' % (time.time() * 1000.0, )})
        request = urllib.request.Request(url + '?' + urllib.parse.urlencode(params),
            headers=merge_dict({
                'User-Agent': self.user_agent,
                'Cache-Control': 'no-cache', }, headers))
        logger.debug(request.full_url)
        with urllib.request.urlopen(request) as f:
            return f.read().decode(f.headers.get_content_charset('utf-8'))

    def post(self, url, params={}, headers={}):
        data = urllib.parse.urlencode(params).encode('ascii')
        request = urllib.request.Request(url + '?' + urllib.parse.urlencode({'x': '%.1f' % (time.time() * 1000.0, )}),
            headers=merge_dict({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Content-Length': len(data),
                'User-Agent': self.user_agent,
                'Cache-Control': 'no-cache', }, headers),
            data=data)
        logger.debug('{} {} {}'.format(request.full_url, request.header_items(), request.data))
        with urllib.request.urlopen(request) as f:
            return f.read().decode(f.headers.get_content_charset('utf-8'))

class Point(object):
    def __init__(self, latitude, longitude):
        self.latitude = float(latitude)
        self.longitude = float(longitude)
        
    def __repr__(self):
        return '<Point: lat={:.1f},lon={:.1f}>'.format(self.latitude, self.longitude)
    
    def __str__(self):
        return '({:.1f},{:.1f})'.format(self.latitude, self.longitude)
    
    def __iter__(self):
        return iter({
            'lat': self.latitude,
            'lot': self.longitude}.items())
        
    def distance_to(self, point):
        radius = 6378.137 # km
        x1 = math.radians(self.longitude)
        y1 = math.radians(self.latitude)
        x2 = math.radians(point.longitude)
        y2 = math.radians(point.latitude)
        dx = x2 - x1
        return radius * math.acos(math.sin(y1) * math.sin(y2) + math.cos(y1) * math.cos(y2) * math.cos(dx))

class ISP(object):
    def __init__(self, name, rating, avg_down, avg_up):
        self.name = name
        self.rating = float(rating)
        self.avg_down = float(avg_down)
        self.avg_up = float(avg_up)
        
    @classmethod
    def fromElement(cls, element):
        self = cls(
            name=element.getAttribute('isp'),
            rating=element.getAttribute('isprating'),
            avg_down=element.getAttribute('ispdlavg'),
            avg_up=element.getAttribute('ispulavg'))
        return self

    def __repr__(self):
        return '<ISP: name="{}",rating={:.1f},avg=(down={:.1f},up={:.1f})>'.format(self.name, self.rating, self.avg_down, self.avg_up)
    
    def __iter__(self):
        return iter({
            'name': self.name,
            'rating': self.rating,
            'average': {'down': self.avg_down, 'up': self.avg_up}}.items())

class Client(object):
    def __init__(self, ipaddr, cc, point, rating, isp):
        self.ipaddr = ipaddr
        self.cc = cc
        self.point = point
        self.rating = float(rating)
        self.isp = isp
        
    @classmethod
    def fromElement(cls, element):
        self = cls(
            ipaddr=element.getAttribute('ip'),
            cc=element.getAttribute('country'),
            point=Point(latitude=element.getAttribute('lat'), longitude=element.getAttribute('lon')),
            rating=element.getAttribute('rating'),
            isp=ISP.fromElement(element))
        return self
        
    def __repr__(self):
        return '<Client: ipaddr={!s},cc="{}",point={!s},rating={:.1f},isp={!r}>'.format(self.ipaddr, self.cc, self.point, self.rating, self.isp)
    
    def __iter__(self):
        return iter({
            'ipaddr': self.ipaddr,
            'cc': self.cc,
            'location': dict(self.point),
            'rating': self.rating,
            'isp': dict(self.isp)}.items())

class Config(object):
    def __init__(self):
        http = HttpClient()
        root = xml.dom.minidom.parseString(http.get('https://www.speedtest.net/speedtest-config.php'))
        settings = {
            'licensekey': root.getElementsByTagName('licensekey')[0].firstChild.data,
            'customer': root.getElementsByTagName('customer')[0].firstChild.data}
        with root.getElementsByTagName('server-config')[0] as e:
            settings['server-config'] = {
                'threadcount': int(e.getAttribute('threadcount')),
                'ignoreids': e.getAttribute('ignoreids'),
                'notonmap': e.getAttribute('notonmap'),
                'forcepingid': e.getAttribute('forcepingid'),
                'preferredserverid': e.getAttribute('preferredserverid')}
        with root.getElementsByTagName('download')[0] as e:
            settings['download'] = {
                'testlength': int(e.getAttribute('testlength')),
                'initialtest': units.Size(e.getAttribute('initialtest')),
                'mintestsize': units.Size(e.getAttribute('mintestsize')),
                'threadsperurl': int(e.getAttribute('threadsperurl'))}
        with root.getElementsByTagName('upload')[0] as e:
            settings['upload'] = {
                'testlength': int(e.getAttribute('testlength')),
                'ratio': int(e.getAttribute('ratio')),
                'initialtest': units.Size(e.getAttribute('initialtest')),
                'mintestsize': units.Size(e.getAttribute('mintestsize')),
                'threads': int(e.getAttribute('threads')),
                'maxchunksize': units.Size(e.getAttribute('maxchunksize')),
                'maxchunkcount': int(e.getAttribute('maxchunkcount')),
                'threadsperurl': int(e.getAttribute('threadsperurl'))}
        with root.getElementsByTagName('latency')[0] as e:
            settings['latency'] = {
                'testlength': int(e.getAttribute('testlength')),
                'waittime': int(e.getAttribute('waittime')),
                'timeout': int(e.getAttribute('timeout'))}
        with root.getElementsByTagName('times')[0] as e:
            settings['times'] = {
                'dl': [int(e.getAttribute('dl1')), int(e.getAttribute('dl2')), int(e.getAttribute('dl3'))],
                'ul': [int(e.getAttribute('ul1')), int(e.getAttribute('ul2')), int(e.getAttribute('ul3'))]}
        logger.debug('{!s}'.format(settings))

        self.client = Client.fromElement(root.getElementsByTagName('client')[0])
        logger.debug('{!r}'.format(self.client))

        upload_ratio = settings['upload']['ratio']
        upload_max = settings['upload']['maxchunkcount']
        upload_sizes = [32768, 65536, 131072, 262144, 524288, 1048576, 7340032][upload_ratio-1:]
        upload_sizes_count = len(upload_sizes)
        upload_count = int(math.ceil(upload_max / upload_sizes_count))

        self.params = {
            'ignore_servers': list(filter(lambda _: int(_), filter(None, settings['server-config']['ignoreids'].split(',')))),
            'upload': {
                'sizes': upload_sizes,
                'counts': upload_count,
                'threads': settings['upload']['threads'],
                'length': settings['upload']['testlength']},
            'download': {
                'sizes': [350, 500, 750, 1000, 1500, 2000, 2500, 3000, 3500, 4000],
                'counts': settings['download']['threadsperurl'],
                'threads': settings['server-config']['threadcount'] * 2,
                'length': settings['download']['testlength']},
            'upload_max': upload_count * upload_sizes_count}
        logger.debug('{!r}'.format(self.params))

class Results(object):
    def __init__(self):
        self.results = []
        self.histgrams = {}
        self.total_size = 0
        self.total_elapsed = 0.0

    def __add__(self, other):
        if not isinstance(other, Results):
            raise TypeError()
        results = Results()
        for result in self.results + other.results:
            results.append(result)
        return results
    
    def __iadd__(self, other):
        if not isinstance(other, Results):
            raise TypeError()
        for result in other.results:
            self.append(result)
        return self
        
    def append(self, result):
        if result['elapsed'] < 0:
            return
        if result['size'] not in self.histgrams:
            self.histgrams[result['size']] = []
        self.histgrams[result['size']].append(result['elapsed'])
        self.total_size += result['size']
        self.total_elapsed += result['elapsed']
        self.results.append(result)
        
    @property
    def histgram(self):
        results = {}
        for size, elapsed in self.histgrams.items():
            results[size] = sum(elapsed) / len(elapsed)
        return results
    
    @property
    def total_bits(self):
        return self.total_size * 8
    
    @property
    def speed(self):
        return self.total_bits / self.total_elapsed

class UploadResults(Results):
    pass

class DownloadResults(Results):
    pass

class SpeedtestNetResult(object):
    def __init__(self, id, hash, rating, timestamp):
        self.id = id
        self.hash = hash
        self.rating = float(rating)
        self._timestamp = timestamp
        
    def __repr__(self):
        return '<SpeedtestNetResult: id={},hash={},rating={},timestamp="{}">'.format(self.id, self.hash, self.rating, self.timestamp)
        
    @classmethod
    def factory(cls, params):
        self = cls(
            id=params['id'],
            hash=params['hash'],
            rating=params['rating'],
            timestamp=datetime.datetime.strptime(params['timestamp'], '%m/%d/%Y %I:%M %p'))
        return self
    
    @property
    def timestamp(self):
        return '%sZ' % self._timestamp.isoformat()
    
    @property
    def image(self):
        return 'http://www.speedtest.net/result/%s.png' % (self.id, )

class TestSuiteResults:
    def __init__(self, testsuite, download, upload):
        self.testsuite = testsuite
        self.download = download
        self.upload = upload
        self._timestamp = datetime.datetime.now(datetime.timezone.utc)

    @property
    def timestamp(self):
        return '%sZ' % self._timestamp.isoformat()
    
    @property
    def server(self):
        return self.testsuite.server
    
    @property
    def client(self):
        return self.testsuite.client
    
    def post(self):
        client = HttpClient()
        #response = client.post('https://www.speedtest.net/api/api.php',
        response = client.post('https://tayhoon.sakura.ne.jp/speedtest/api/api.php',
            headers={
                'Referer': 'http://c.speedtest.net/flash/speedtest.swf'},
            params={
                'recommendedserverid': self.server.id,
                'ping': int(round(self.server.latency, 0)),
                'screenresolution': '',
                'promo': '',
                'download': int(round(self.download.speed / 1000.0, 0)),
                'screendpi': '',
                'upload': int(round(self.upload.speed / 1000.0, 0)),
                'testmethod': 'http',
                'hash': hashlib.md5(('%.0f-%.0f-%.0f-%s' % (round(self.server.latency, 0), round(self.upload.speed / 1000.0), round(self.download.speed / 1000.0), '297aae72', )).encode('utf-8')).hexdigest(),
                'touchscreen': 'none',
                'startmode': 'pingselect',
                'accuracy': 1,
                'bytesreceived': self.download.total_size,
                'bytessent': self.upload.total_size,
                'serverid': self.server.id,
                    })
        params = urllib.parse.parse_qs(response)
        logger.debug('{} {}'.format(response, params))
        return {
            'id': params.get('resultid', ['0'])[0],
            'hash': params.get('hash_key_id', [''])[0],
            'rating': params.get('rating', [0.0])[0],
            'timestamp': '%s %s' % (params.get('date', ['1/1/1970'])[0], params.get('time', ['00:00 AM'])[0], )}
    
    @property
    @memoized
    def speedtestnet(self):
        return SpeedtestNetResult.factory(self.post())
    
    def csv(self):
        fieldnames = ['Server ID', 'Sponsor', 'Server Name', 'Timestamp', 'Distance', 'Ping', 'Download', 'Upload', 'Share', 'IP Address']
        buff = io.StringIO(newline='')
        f = csv.DictWriter(buff, fieldnames=fieldnames)
        f.writeheader()
        f.writerow({
            'Server ID': self.server.id,
            'Sponsor': self.server.sponsor,
            'Server Name': self.server.name,
            'Timestamp': self.timestamp,
            'Distance': self.server.distance,
            'Ping': self.server.latency,
            'Download': self.download.speed,
            'Upload': self.upload.speed,
            'Share': '', # self.speedtestnet.image
            'IP Address': self.client.ipaddr
                })
        return buff.getvalue()
    
    def json(self):
        return json.dumps({
            'download': self.download.speed,
            'upload': self.upload.speed,
            'ping': self.server.latency,
            'server': dict(self.server),
            'timestamp': self.timestamp,
            'bytes_sent': self.upload.total_size,
            'bytes_received': self.download.total_size,
            'share': '', # self.speedtestnet.image
            'client': dict(self.client)}, indent=4)

class HTTPUploadData(io.BytesIO):
    def __init__(self, size):
        super().__init__()
        chars = b'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        self.write(b'content1=')
        for _ in range(size // len(chars) + 1):
            self.write(chars)
        self.truncate(size)
        self.seek(0, os.SEEK_SET)
        self._size = size
        
    @property
    def size(self):
        return self._size
    
    @property
    def mime_type(self):
        return 'application/x-www-form-urlencoded'

class HTTPUploadData0(object):
    def __init__(self, size):
        self.closed = False
        self.curr = 0
        self._size = size

    def __del__(self):
        self.close()

    @property
    def size(self):
        return self._size

    @property
    def mime_type(self):
        return 'application/x-www-form-urlencoded'

    def close(self):
        self.closed = True

    def fileno(self):
        raise OSError()
    
    def flush(self):
        pass

    def seekable(self):
        return True

    def seek(self, offset, whence=os.SEEK_SET):
        if whence == os.SEEK_SET:
            self.curr = offset
        elif whence == os.SEEK_CUR:
            self.curr += offset
        elif whence == os.SEEK_END:
            self.curr = self._size + offset
        if self.curr < 0:
            self.curr = 0
        if self._size < self.curr:
            self.curr = self._size

    def tell(self):
        return self.curr

    def truncate(self, size=None):
        if size < 0:
            return self._size
        if size is None:
            self._size = self.curr
        else:
            self._size = size
        return self._size
    
    def writable(self):
        return True

    def write(self, b):
        pass
    
    def readable(self):
        return True

    def read(self, size=-1):
        first = b'content1='
        chars = b'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'

        if size < 0:
            size = self._size
        result = b''
        if self.curr < len(first) and 0 < size and self.curr < self._size:
            p = self.curr
            x = first[p:p+min(size, self._size - self.curr)]
            size -= len(x)
            self.curr += len(x)
            result += x
        while 0 < size and self.curr < self._size:
            p = (self.curr - len(first)) % len(chars)
            x = chars[p:p+min(size, self._size - self.curr)]
            size -= len(x)
            self.curr += len(x)
            result += x
        if self._size < self.curr:
            self.curr = self._size
        return result

class HTTPCancelableUploadData(HTTPUploadData):
    def __init__(self, size, terminated):
        super().__init__(size)
        #self.terminated = terminated
        
    def read(self, size):
        result = b''
        chunksize = 8*1024
        while True: # not self.terminated.is_set():
            data = super().read(size if size < chunksize else chunksize)
            result += data
            if len(data) < chunksize:
                break
            size -= len(data)
        return result

class HTTPUploader(threading.Thread, HttpClient):
    def __init__(self, resultq, requestq, terminated, version='both'):
        super().__init__()
        self.version = version
        self.requestq = requestq
        self.resultq = resultq
        self.terminated = terminated

    def run(self):
        def http_connection_cls(url):
            return {
                'http': http.client.HTTPConnection, 
                'https': http.client.HTTPSConnection, }[url.scheme]

        def http_upload_data_cls(preallocate=True):
            return [
                HTTPUploadData0,
                HTTPUploadData][bool(preallocate)]

        while not self.terminated.wait(timeout=0.1):
            try:
                url, size = self.requestq.get(timeout=0.1)
                netloc = url.netloc
                if self.version == 'ipv4':
                    netloc = '%s:%d' % (url.resolve4, url.port)
                elif self.version == 'ipv6':
                    netloc = '[%s]:%d' % (url.resolve6, url.port)
                data = http_upload_data_cls(preallocate=True)(size=size)
                conn = http_connection_cls(url)(netloc)
                start = time.time()
                conn.request(
                    'POST', url.anticache.path,
                    headers={
                        'Host': url.hostname,
                        'User-Agent': self.user_agent,
                        'Cache-Control': 'no-cache',
                        'Content-Type': data.mime_type,
                        'Content-Length': data.size, },
                    body=data)
                response = conn.getresponse()
                response.read()
                finish = time.time()
                self.resultq.put({'size': data.size, 'elapsed': finish - start, })
                # request = urllib.request.Request(url.anticache,
                #     method='POST',
                #     headers={
                #         'User-Agent': self.user_agent,
                #         'Cache-Control': 'no-cache',
                #         'Content-Type': data.mime_type,
                #         'Content-Length': data.size, },
                #     data=data)
                # start = time.time()
                # with urllib.request.urlopen(request) as f:
                #     f.read()
                #     finish = time.time()
                # self.resultq.put({'size': int(request.get_header('Content-length')), 'elapsed': finish - start, })
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(e)
                self.resultq.put({'size': 0, 'elapsed': -1, })

class HTTPDownloader(threading.Thread, HttpClient):
    def __init__(self, resultq, requestq, terminated, version='both'):
        super().__init__()
        self.version = version
        self.requestq = requestq
        self.resultq = resultq
        self.terminated = terminated
        
    def run(self):
        def http_connection_cls(url):
            return {
                'http': http.client.HTTPConnection, 
                'https': http.client.HTTPSConnection, }[url.scheme]

        while not self.terminated.wait(timeout=0.1):
            try:
                url = self.requestq.get(timeout=0.1)
                netloc = url.netloc
                if self.version == 'ipv4':
                    netloc = '%s:%d' % (url.resolve4, url.port)
                elif self.version == 'ipv6':
                    netloc = '[%s]:%d' % (url.resolve6, url.port)
                conn = http_connection_cls(url)(netloc)
                start = time.time()
                conn.request(
                    'GET', url.anticache.path,
                    headers={
                        'Host': url.hostname,
                        'User-Agent': self.user_agent,
                        'Cache-Control': 'no-cache', })
                response = conn.getresponse()
                data = response.read()
                finish = time.time()
                size = int(response.getheader('Content-Length', len(data)))
                # request = urllib.request.Request(url.anticache,
                #     method='GET',
                #     headers={
                #         'User-Agent': self.user_agent,
                #         'Cache-Control': 'no-cache', })
                # start = time.time()
                # with urllib.request.urlopen(request) as f:
                #     data = f.read()
                #     finish = time.time()
                #     size = int(f.headers.get('Content-Length', len(data)))
                self.resultq.put({'size': size, 'elapsed': finish - start, })
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(e)
                self.resultq.put({'size': 0, 'elapsed': -1, })

class HTTPCancelableDownloader(HTTPDownloader):
    def run(self):
        while not self.terminated.wait(timeout=0.1):
            try:
                total = 0
                chunksize = 8*1024
                request = self.requestq.get(timeout=0.1)
                request.add_header('User-Agent', self.user_agent)
                start = time.time()
                with urllib.request.urlopen(request) as f:
                    while not self.terminated.is_set():
                        data = f.read(chunksize)
                        total += len(data)
                        if len(data) < chunksize:
                            break
                    finish = time.time()
                    size = int(f.headers.get('Content-Length', len(data)))
                if total < size:
                    raise Exception()
                self.resultq.put({'size': size, 'elapsed': finish - start, })
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(e)
                self.resultq.put({'size': 0, 'elapsed': -1, })

class Server(object):
    def __init__(self, testsuite, id, name, url, host, country, cc, sponsor, point):
        self.testsuite = testsuite
        self.id = int(id)
        self.name = name
        self.url = URL(url)
        self.host = host
        self.country = country
        self.cc = cc
        self.sponsor = sponsor
        self.point = point
        
    @classmethod
    def fromElement(cls, testsuite, element):
        self = cls(
            testsuite=testsuite,
            id=int(element.getAttribute('id')),
            name=element.getAttribute('name'),
            url=element.getAttribute('url'),
            host=element.getAttribute('host'),
            country=element.getAttribute('country'),
            cc=element.getAttribute('cc'),
            sponsor=element.getAttribute('sponsor'),
            point=Point(latitude=element.getAttribute('lat'), longitude=element.getAttribute('lon')))
        logger.debug('{!r}'.format(self))
        return self
        
    def __repr__(self):
        return '<Server: id={},name="{}",country="{}",cc="{}",url="{}",host="{}",sponsor="{}",point={!s},distance={:.2f},ipv4={},ipv6={}>'.format(self.id, self.name, self.country, self.cc, self.url.value, self.host, self.sponsor, self.point, self.distance, self.support_ipv4, self.support_ipv6)
    
    def __str__(self):
        return '{id}) {sponsor} ({name}, {country}) [{distance:.2f}km]'.format(
            id=self.id,
            sponsor=self.sponsor,
            name=self.name,
            country=self.country,
            distance=self.distance)
    
    def __iter__(self):
        return iter({
            'id': self.id,
            'name': self.name,
            'url': self.url.value,
            'host': self.host,
            'country': self.country,
            'cc': self.cc,
            'sponsor': self.sponsor,
            'location': dict(self.point)}.items())
    
    @property
    def support_ipv4(self):
        return self.url.can_resolve4()

    @property
    def support_ipv6(self):
        return self.url.can_resolve6()
    
    @property
    @memoized
    def distance(self):
        return self.testsuite.client.point.distance_to(self.point)
    
    @property
    @memoized
    def latency(self):
        def http_connection_cls(scheme):
            return {
                'http': http.client.HTTPConnection, 
                'https': http.client.HTTPSConnection, }[scheme]

        latencies = []
        for _ in range(3):
            conn = http_connection_cls(self.url.scheme)(self.url.netloc)
            try:
                start = time.perf_counter()
                conn.request(
                    'GET', self.url.join('/latency.txt').anticache.path,
                    headers={
                        'Host': self.url.hostname,
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
                        'Cache-Control': 'no-cache', })
                response = conn.getresponse()
                latency = time.perf_counter() - start
                if not (response.status == 200 and response.read(9) == b'test=test'):
                    raise HttpRetrievalError()
                latencies.append(latency)
                logger.debug('{!s} GET {} => {} {!s}'.format(self.url.hostname, self.url.join('/latency.txt').anticache.path, response.status, latencies))
            except (urllib.error.HTTPError, urllib.error.URLError, socket.error, ssl.SSLError, ssl.CertificateError, http.client.BadStatusLine, HttpRetrievalError) as e:
                logger.error(e)
                latencies.append(3600.0)
            finally:
                if conn:
                    conn.close()
                conn = None
        return round((sum(latencies) / (len(latencies)*2)) * 1000.0, 3)
    ping=latency
    
    def do_download(self, threads=2):
        terminated = threading.Event()
        requestq = multiprocessing.Queue()
        resultq = multiprocessing.Queue()
        for _ in range(threads):
            HTTPDownloader(resultq=resultq, requestq=requestq, terminated=terminated, version=self.testsuite.ip_version).start()
        
        request_paths = []
        for size in self.testsuite.config.params['download']['sizes']:
            for _ in range(self.testsuite.config.params['download']['counts']):
                request_paths.append('/random%sx%s.jpg' % (size, size, ))
                
        for request_path in request_paths:
            requestq.put(self.url.join(request_path))
        
        results = DownloadResults()
        for _ in range(len(request_paths)):
            results.append(resultq.get())
        terminated.set()
        return results
        
    def do_upload(self, threads=2):
        terminated = threading.Event()
        requestq = multiprocessing.Queue()
        resultq = multiprocessing.Queue()
        for _ in range(threads):
            HTTPUploader(resultq=resultq, requestq=requestq, terminated=terminated, version=self.testsuite.ip_version).start()
        
        sizes = []
        for size in self.testsuite.config.params['upload']['sizes']:
            for _ in range(self.testsuite.config.params['upload']['counts']):
                sizes.append(size)

        for size in sizes:
            requestq.put((self.url, size))
        
        results = UploadResults()
        for _ in range(len(sizes)):
            results.append(resultq.get())
        terminated.set()
        return results

    @property
    @memoized
    def download(self):
        return self.do_download()

    @property
    @memoized
    def upload(self):
        return self.do_upload()

class MiniServer(Server):
    def __init__(self, testsuite, url):
        def count_lines(value):
            return len(value.strip().splitlines())
        
        logger.debug(url)
        url = urllib.parse.urlparse(url)
        dirname, basename = os.path.split(url.path)
        root, ext = os.path.splitext(url.path)
        logger.debug('dirname="{}" basename="{}" root="{}" ext="{}"'.format(dirname, basename, root, ext))

        # Extract dir name only        
        if ext:
            request_url = urllib.parse.urljoin(url.geturl(), dirname)
        else:
            request_url = url.geturl().rstrip('/')
        logger.debug(request_url)
        
        client = HttpClient()
        response = client.get(request_url)
        extensions = re.findall(r'upload_?[Ee]xtension: "([^"]+)"', response)
        if not extensions:
            for ext in ('php', 'asp', 'aspx', 'jsp'):
                try:
                    response = client.get(request_url + '/speedtest/upload.%s' % (ext, ))
                    if count_lines(response) == 1 and re.match(r'size=[0-9]', response):
                        extensions = [ext]
                        break
                except Exception:
                    pass
        
        logger.debug(extensions)
        if not extensions:
            raise Exception()
        
        super().__init__(testsuite,
            id=0,
            name=url.netloc,
            url=request_url + '/speedtest/upload.%s' % (extensions[0], ),
            host='',
            country='',
            cc='',
            sponsor='Speedtest Mini',
            point=Point(0.0, 0.0))
    
    @property
    def distance(self):
        return 0.0
        
    @property
    def latency(self):
        return 0.0

class NullServer(Server):
    def __init__(self, testsuite):
        super().__init__(testsuite,
            id=0,
            name='Speedtest Null Server',
            url='https://tayhoon.sakura.ne.jp/speedtest/upload.php',
            host='tayhoon.sakura.ne.jp',
            country='Japan',
            cc='JP',
            sponsor='(Sponsor Name)',
            point=Point(0.0, 0.0))
    
    @property
    def distance(self):
        return 0.0
        
    @property
    def latency(self):
        return 0.0

class Servers(object):
    def __init__(self, testsuite):
        self.testsuite = testsuite

    @property
    @memoized
    def servers(self):
        servers = []
        http = HttpClient()
        urls = [
            'https://www.speedtest.net/speedtest-servers-static.php',
            'http://c.speedtest.net/speedtest-servers-static.php',
            'https://www.speedtest.net/speedtest-servers.php',
            'http://c.speedtest.net/speedtest-servers.php', ]
        for url in urls:
            root = xml.dom.minidom.parseString(http.get(url, params={'threads': self.testsuite.config.params['download']['threads']}))
            for element in root.getElementsByTagName('server'):
                server = Server.fromElement(self.testsuite, element)
                if server.id in self.testsuite.config.params['ignore_servers'] + self.testsuite.option.args.exclude:
                    continue
                servers.append(server)
        if self.testsuite.ip_version == 'ipv4':
            return list(filter(lambda server: server.support_ipv4, servers))
        elif self.testsuite.ip_version == 'ipv6':
            return list(filter(lambda server: server.support_ipv6, servers))
        return servers
    
    def __iter__(self):
        self._iter_index = 0
        return self
    
    def __next__(self):
        if self._iter_index < len(self.servers):
            result = self.servers[self._iter_index]
            self._iter_index += 1
            return result
        raise StopIteration()
    
    def findById(self, id):
        for server in self.servers:
            if server.id == id:
                return server
        raise Exception('Not Found')
    
    def findByUrl(self, url):
        for server in self.servers:
            if server.url == url:
                return server
        raise Exception('Not Found')
                
    def get_closest_servers(self, limit=5):
        def sort_by_distance(servers):
            return sorted(servers, key=lambda server: server.distance)
        return sort_by_distance(self.servers)[:limit]

class TestSuite(object):
    def __init__(self, option):
        self.config = Config()
        self.option = option
        
    @property
    def client(self):
        return self.config.client
        
    @property
    @memoized
    def servers(self):
        return Servers(self)
    
    def get_best_server(self):
        def sort_by_latency(servers):
            return sorted(servers, key=lambda server: server.latency)
        return sort_by_latency(self.servers.get_closest_servers())[0]
    
    @property
    def ip_version(self):
        if self.option.args.ipv6 and not self.option.args.ipv4:
            return 'ipv6'
        elif self.option.args.ipv4 and not self.option.args.ipv6:
            return 'ipv4'
        return 'both'
    
    @property
    @memoized
    def server(self):
        return self.get_best_server()
    
    def do_download(self):
        return self.server.do_download()

    def do_upload(self):
        return self.server.do_upload()

    @property
    @memoized
    def download(self):
        return self.do_download()

    @property
    @memoized
    def upload(self):
        return self.do_upload()
    
    @property
    @memoized
    def results(self):
        return TestSuiteResults(self, self.download, self.upload)

class NullOption(object):
    @dataclasses.dataclass
    class Namespace:
        exclude: list = dataclasses.field(default_factory=list)
        pre_allocate: bool = True
        single: bool = False
        timeout: float = 10.0
        ipv4: bool = True
        ipv6: bool = True
    
    @property
    def args(self):
        return self.Namespace()

def main():
    logger.setLevel(logging.DEBUG)
    u = URL('https://www.speedtest.net')
    print(u.port)
    print(u.can_resolve4())
    print(u.can_resolve6())
    print(u.addrinfo)
    print(u.addrinfo4)
    print(u.addrinfo6)
    print(u.resolve4)
    print(u.resolve6)
        
    t = TestSuite(option=NullOption())
    print('== Selected Server')
    print(t.server)
    print('{}km'.format(t.server.distance))
    print('{}pt'.format(t.server.latency))
    print('{}ms'.format(t.server.ping))
    print('== Download Results')
    for size, elapsed in t.results.download.histgram.items():
        print('{!s}B / {:.1f}s => {!s}bps'.format(units.Size(size), elapsed, units.Bandwidth(size*8/elapsed)))
    print('{!s}B / {:.1f}s => {!s}bps'.format(units.Size(t.results.download.total_size), t.results.download.total_elapsed, units.Bandwidth(t.results.download.speed)))
    print('== Upload Results')
    for size, elapsed in t.results.upload.histgram.items():
        print('{!s}B / {:.1f}s => {!s}bps'.format(units.Size(size), elapsed, units.Bandwidth(size*8/elapsed)))
    print('{!s}B / {:.1f}s => {!s}bps'.format(units.Size(t.results.upload.total_size), t.results.upload.total_elapsed, units.Bandwidth(t.results.upload.speed)))
    print(t.results.json())
    print(t.results.csv())
    print(t.results.speedtestnet)
    print(t.results.speedtestnet.image)

if __name__ == '__main__':
    main()