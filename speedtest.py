#!/usr/local/bin/python3
# encoding: utf-8

from functools import wraps
import math
import time
import ipaddress
import platform
import ssl
import http.client
import urllib.request
import urllib.parse
import xml.dom
import xml.dom.minidom

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
    
    def get(self, url, params={}):
        params.update({'x': '%s.0' % int(time.time() * 1000)})
        request = urllib.request.Request(url + '?' + urllib.parse.urlencode(params),
            headers={
                'User-Agent': self.user_agent,
                'Cache-Control': 'no-cache', })
        print(request.full_url)
        with urllib.request.urlopen(request) as f:
            return f.read()

    def post(self, url, params={}):
        request = urllib.request.Request(url + '?' + urllib.parse.urlencode({'x': '%s.0' % int(time.time() * 1000)}),
            headers={
                'User-Agent': self.user_agent, # Header "Content-Type: application/x-www-form-urlencoded" will be added as a default.
                'Cache-Control': 'no-cache', },
            data=urllib.parse.urlencode(params).encode('ascii'))
        print(request.full_url)
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
        return '<ISP: name="{}",rating={:.1f},avg_down={:.1f},avg_up={:.1f}>'.format(self.name, self.rating, self.avg_down, self.avg_up)

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
        return '<Client: ipaddr={!s},cc="{}",point={!s},rating={:.1f},isp={!s}>'.format(self.ipaddr, self.cc, self.point, self.rating, self.isp)

class Config(object):
    def __init__(self):
        http = HttpClient()
        root = xml.dom.minidom.parseString(http.get('https://www.speedtest.net/speedtest-config.php').decode('utf-8'))

        e = {
            'server-config': root.getElementsByTagName('server-config')[0],
            'download': root.getElementsByTagName('download')[0],
            'upload': root.getElementsByTagName('upload')[0], }

        ratio = int(e['upload'].getAttribute('ratio'))
        upload_max = int(e['upload'].getAttribute('maxchunkcount'))
        
        up_sizes = [32768, 65536, 131072, 262144, 524288, 1048576, 7340032]
        
        sizes = {
            'upload': up_sizes[ratio-1:],
            'download': [350, 500, 750, 1000, 1500, 2000, 2500, 3000, 3500, 4000], }
        size_count = len(sizes['upload'])
        upload_count = int(math.ceil(upload_max / size_count))
        
        self.p = {
            'client': Client.fromElement(root.getElementsByTagName('client')[0]),
            'ignore_servers': list(filter(lambda _: int(_), filter(None, e['server-config'].getAttribute('ignoreids').split(',')))),
            'sizes': sizes,
            'counts': {
                'upload': upload_count,
                'download': int(e['download'].getAttribute('threadsperurl')), },
            'threads': {
                'upload': int(e['upload'].getAttribute('threads')),
                'download': int(e['server-config'].getAttribute('threadcount')) * 2, },
            'length': {
                'upload': int(e['upload'].getAttribute('testlength')),
                'download': int(e['download'].getAttribute('testlength')), },
            'upload_max': upload_count * size_count, }
        print(self.p)

class Server(object):
    def __init__(self, testsuite, id, name, url, host, country, cc, sponsor, point):
        self.testsuite = testsuite
        self.id = id
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
            id=element.getAttribute('id'),
            name=element.getAttribute('name'),
            url=element.getAttribute('url'),
            host=element.getAttribute('host'),
            country=element.getAttribute('country'),
            cc=element.getAttribute('cc'),
            sponsor=element.getAttribute('sponsor'),
            point=Point(latitude=element.getAttribute('lat'), longitude=element.getAttribute('lon')))
        print(self)
        return self
        
    def __repr__(self):
        return '<Server: id={},name="{}",country="{}",cc="{}",url="{}",host="{}",sponsor="{}",point={!s},distance={:.2f}>'.format(self.id, self.name, self.country, self.cc, self.url, self.host, self.sponsor, self.point, self.distance)
    
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

        url = urllib.parse.urlparse(self.url, allow_fragments=False)
        times = 3
        latencies = []
        for _ in range(times):
            request_url = urllib.parse.urlparse('%s://%s/latency.txt?%s' % (url.scheme, url.netloc, urllib.parse.urlencode({'x': '%s.%s' % (int(time.time() * 1000), _, )}), ), allow_fragments=False)
            request_path = '%s?%s' % (request_url.path, request_url.query, ) 
            try:
                conn = get_http_connection_cls(request_url.scheme)(request_url.netloc)
                start = time.perf_counter()
                conn.request('GET', request_path, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'})
                response = conn.getresponse()
                latency = time.perf_counter() - start
                if not (response.status == 200 and response.read(9) == b'test=test'):
                    raise HttpRetrievalError()
                latencies.append(latency)
                print(request_url, 'GET', request_path, response.status, latencies)
            except (HTTPError, URLError, socket.error, ssl.SSLError, ssl.CertificateError, BadStatusLine, HttpRetrievalError) as e:
                latencies.append(3600.0)
            finally:
                if conn:
                    conn.close()
                conn = None
        return round((sum(latencies) / (times*2)) * 1000.0, 3)

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

class Servers(object):
    def __init__(self, testsuite):
        self.servers = []
        self.testsuite = testsuite

        http = HttpClient()
        urls = [
            'https://www.speedtest.net/speedtest-servers-static.php',
            'http://c.speedtest.net/speedtest-servers-static.php',
            'https://www.speedtest.net/speedtest-servers.php',
            'http://c.speedtest.net/speedtest-servers.php', ]
        for url in urls:
            root = xml.dom.minidom.parseString(http.get(url, params={'threads': testsuite.config.p['threads']['download']}).decode('utf-8'))
            for server in root.getElementsByTagName('server'):
                self.servers.append(Server.fromElement(testsuite, server))
                
    def get_closest_servers(self, limit=5):
        def sort_by_distance(servers):
            return sorted(servers, key=lambda server: server.distance)
        return sort_by_distance(self.servers)[:limit]

class TestSuite(object):
    def __init__(self):
        self.config = Config()
        
    @property
    def client(self):
        return self.config.p['client']
        
    @property
    def servers(self):
        return Servers(self)
    
    def get_best_server(self):
        def sort_by_latency(servers):
            return sorted(servers, key=lambda server: server.latency)
        return sort_by_latency(self.servers.get_closest_servers())[0]

def main():
    #http = HttpClient()
    #print(http.get(str(URL('//tayhoon.sakura.ne.jp/_.php'))).decode('utf-8'))
    t = TestSuite()
    print(t.servers.get_closest_servers())
    print(t.get_best_server())

if __name__ == '__main__':
    main()