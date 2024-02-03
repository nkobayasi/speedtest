#!/usr/local/bin/python3
# encoding: utf-8

from functools import wraps
from dataclasses import dataclass
import io
import os
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
import http.client
import urllib.request
import urllib.parse
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

class StderrHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__()
        self.setFormatter(logging.Formatter('[%(process)d] %(message)s'))

class SyslogHandler(logging.handlers.SysLogHandler):
    def __init__(self, filename):
        super().__init__()
        self.setFormatter(logging.Formatter('%(levelname)s: %(name)s.%(funcName)s(): %(message)s'))

class FileHandler(logging.handlers.WatchedFileHandler):
    def __init__(self, filename):
        super().__init__(filename, encoding='utf-8')
        self.setFormatter(logging.Formatter('[%(asctime)s] [%(process)d] %(levelname)s: %(name)s.%(funcName)s(): %(message)s'))

logger = logging.getLogger('ping').getChild(__name__)
logger.addHandler(StderrHandler())

class HttpRetrievalError(Exception): pass

class URL(object):
    def __init__(self, url, secure=True):
        self.full = urllib.parse.urljoin(('http://', 'https://')[bool(secure)], url)
    
    def __repr__(self):
        return '<URL: {}>'.format(self.full)
        
    def __str__(self):
        return self.full
    
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
            return f.read()

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
            return f.read()

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
        radius = 6371  # km
        dlat = math.radians(point.latitude - self.latitude)
        dlon = math.radians(point.longitude - self.longitude)
        a = (math.sin(dlat / 2) * math.sin(dlat / 2) +
             math.cos(math.radians(self.latitude)) *
             math.cos(math.radians(point.latitude)) * 
             math.sin(dlon / 2) * math.sin(dlon / 2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return radius * c

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
            isp=ISP(
                name=element.getAttribute('isp'),
                rating=element.getAttribute('isprating'),
                avg_down=element.getAttribute('ispdlavg'),
                avg_up=element.getAttribute('ispulavg')))
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
        root = xml.dom.minidom.parseString(http.get('https://www.speedtest.net/speedtest-config.php').decode('utf-8'))
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
        return float(self.total_bits) / self.total_elapsed

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
        self._timestamp = datetime.datetime.utcnow()

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
                    }).decode('utf-8')
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
        for _ in range(int(round(float(size) / len(chars))) + 1):
            self.write(chars)
        self.truncate(size)
        self.seek(0, os.SEEK_SET)

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
    def __init__(self, resultq, requestq, terminated):
        super().__init__()
        self.requestq = requestq
        self.resultq = resultq
        self.terminated = terminated

    def run(self):
        while not self.terminated.wait(timeout=0.1):
            try:
                request = self.requestq.get(timeout=0.1)
                request.add_header('User-Agent', self.user_agent)
                start = time.time()
                with urllib.request.urlopen(request) as f:
                    f.read()
                    finish = time.time()
                self.resultq.put({'size': int(request.get_header('Content-length')), 'elapsed': finish - start, })
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(e)
                self.resultq.put({'size': 0, 'elapsed': -1, })

class HTTPDownloader(threading.Thread, HttpClient):
    def __init__(self, resultq, requestq, terminated):
        super().__init__()
        self.requestq = requestq
        self.resultq = resultq
        self.terminated = terminated
        
    def run(self):
        while not self.terminated.wait(timeout=0.1):
            try:
                request = self.requestq.get(timeout=0.1)
                request.add_header('User-Agent', self.user_agent)
                start = time.time()
                with urllib.request.urlopen(request) as f:
                    f.read()
                    finish = time.time()
                    size = int(f.headers['Content-Length'])
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
                    size = int(f.headers['Content-Length'])
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
        self.url = url
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
        return '<Server: id={},name="{}",country="{}",cc="{}",url="{}",host="{}",sponsor="{}",point={!s},distance={:.2f}>'.format(self.id, self.name, self.country, self.cc, self.url, self.host, self.sponsor, self.point, self.distance)
    
    def __iter__(self):
        return iter({
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'host': self.host,
            'country': self.country,
            'cc': self.cc,
            'sponsor': self.sponsor,
            'location': dict(self.point)}.items())
    
    @property
    @memoized
    def distance(self):
        return self.testsuite.client.point.distance_to(self.point)
    
    @property
    @memoized
    def latency(self):
        def get_http_connection_cls(scheme):
            return {
                'http': http.client.HTTPConnection, 
                'https': http.client.HTTPSConnection, }[scheme]

        latencies = []
        for _ in range(3):
            request_url = urllib.parse.urlparse(urllib.parse.urljoin(self.url, '/latency.txt?%s' % (urllib.parse.urlencode({'x': '%.0f.%d' % (time.time() * 1000.0, _, )}), )), allow_fragments=False)
            request_path = '%s?%s' % (request_url.path, request_url.query, ) 
            try:
                conn = get_http_connection_cls(request_url.scheme)(request_url.netloc)
                start = time.perf_counter()
                conn.request('GET', request_path, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
                    'Cache-Control': 'no-cache', })
                response = conn.getresponse()
                latency = time.perf_counter() - start
                if not (response.status == 200 and response.read(9) == b'test=test'):
                    raise HttpRetrievalError()
                latencies.append(latency)
                logger.debug('{!s} GET {} => {} {!s}'.format(request_url, request_path, response.status, latencies))
            except (HTTPError, URLError, socket.error, ssl.SSLError, ssl.CertificateError, BadStatusLine, HttpRetrievalError) as e:
                logger.error(e)
                latencies.append(3600.0)
            finally:
                if conn:
                    conn.close()
                conn = None
        return round((sum(latencies) / (len(latencies)*2)) * 1000.0, 3)
    ping=latency
    
    def do_download(self):
        terminated = threading.Event()
        requestq = multiprocessing.Queue()
        resultq = multiprocessing.Queue()
        for _ in range(2):
            HTTPDownloader(resultq=resultq, requestq=requestq, terminated=terminated).start()
        
        request_paths = []
        for size in self.testsuite.config.params['download']['sizes']:
            for _ in range(self.testsuite.config.params['download']['counts']):
                request_paths.append('/random%sx%s.jpg' % (size, size, ))
                
        i = 0
        for request_path in request_paths:
            request = urllib.request.Request(urllib.parse.urljoin(self.url, request_path + '?' + urllib.parse.urlencode({'x': '%.0f.%d' % (time.time() * 1000.0, i, )})),
                method='GET',
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
                    'Cache-Control': 'no-cache', })
            logger.debug(request.full_url)
            requestq.put(request)
            i += 1
        
        results = DownloadResults()
        for _ in range(len(request_paths)):
            results.append(resultq.get())
        terminated.set()
        return results
        
    def do_upload(self):
        terminated = threading.Event()
        requestq = multiprocessing.Queue()
        resultq = multiprocessing.Queue()
        for _ in range(2):
            HTTPUploader(resultq=resultq, requestq=requestq, terminated=terminated).start()
        
        sizes = []
        for size in self.testsuite.config.params['upload']['sizes']:
            for _ in range(self.testsuite.config.params['upload']['counts']):
                sizes.append(size)

        for size in sizes:
            data = HTTPUploadData(size=size)
            request = urllib.request.Request(self.url,
                method='POST',
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
                    'Cache-Control': 'no-cache',
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Content-Length': size, },
                data=data)
            logger.debug(request.full_url)
            requestq.put(request)
        
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
    def __init__(self, testsuite):
        server = testsuite.servers.servers[0]
        super().__init__(testsuite,
            id=0,
            name='Speedtest Mini Server',
            url=server.url,
            host=server.host,
            country=server.country,
            cc=server.cc,
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
            name='Speedtest Mini Server',
            url='http://sp5.atcc-gns.net:8080/speedtest/upload.php',
            host='sp5.atcc-gns.net:8080',
            country='Japan',
            cc='JP',
            sponsor='Speedtest Mini',
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
            root = xml.dom.minidom.parseString(http.get(url, params={'threads': self.testsuite.config.params['download']['threads']}).decode('utf-8'))
            for element in root.getElementsByTagName('server'):
                server = Server.fromElement(self.testsuite, element)
                if server.id in self.testsuite.config.params['ignore_servers']:
                    continue
                servers.append(server)
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
    def __init__(self):
        self.config = Config()
        
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
        return self.server.do_download()

    @property
    @memoized
    def upload(self):
        return self.server.do_upload()
    
    @property
    @memoized
    def results(self):
        return TestSuiteResults(self, self.server.do_download(), self.server.do_upload())

def main():
    logger.setLevel(logging.DEBUG)
    t = TestSuite()
    print('== Selected Server')
    print(t.server)
    print('{}km'.format(t.server.distance))
    print('{}pt'.format(t.server.latency))
    print('== Download Results')
    for size, elapsed in t.results.download.histgram.items():
        print('{!s}B / {:.1f}s => {!s}bps'.format(units.Size(size), elapsed, units.Bandwidth(size*8.0/elapsed)))
    print('{!s}B / {:.1f}s => {!s}bps'.format(units.Size(t.results.download.total_size), t.results.download.total_elapsed, units.Bandwidth(t.results.download.speed)))
    print('== Upload Results')
    for size, elapsed in t.results.upload.histgram.items():
        print('{!s}B / {:.1f}s => {!s}bps'.format(units.Size(size), elapsed, units.Bandwidth(size*8.0/elapsed)))
    print('{!s}B / {:.1f}s => {!s}bps'.format(units.Size(t.results.upload.total_size), t.results.upload.total_elapsed, units.Bandwidth(t.results.upload.speed)))
    r = t.results.download
    print(r.results, r.total_size)
    r = r + r
    print(r.results, r.total_size)
    print(t.results.json())
    print(t.results.csv())
    print(t.results.speedtestnet)
    print(t.results.speedtestnet.image)

if __name__ == '__main__':
    main()