#!/usr/local/bin/python3
# encoding: utf-8

import sys
import argparse
import speedtest

import units

class Option(object):
    def __init__(self):
        self.prog = 'speedtest-cli'
        parser = argparse.ArgumentParser(
            prog=self.prog,
            description=(
                'Command line interface for testing internet bandwidth using speedtest.net.\n'
                '--------------------------------------------------------------------------\n'
                'https://github.com/nkobayasi/speedtest-cli'))
        parser.add_argument('-v', '--version', action='store_true', help='Show the version number and exit')
        parser.add_argument('--no-download', action='store_false', dest='download', help='Do not perform download test')
        parser.add_argument('--no-upload', action='store_false', dest='upload', help='Do not perform upload test')
        parser.add_argument('--single', action='store_true', help='Only use a single connection instead of multiple. This simulates a typical file transfer.')
        parser.add_argument('--bytes', action='store_const', const=('byte', 8), default=('bit', 1), dest='units', help='Display values in bytes instead of bits. Does not affect the image generated by --share, nor output from --json or --csv')
        parser.add_argument('--share', action='store_true', help='Generate and provide a URL to the speedtest.net share results image, not displayed with --csv')
        parser.add_argument('--simple', action='store_true', help='Suppress verbose output, only show basic information')
        parser.add_argument('--csv', action='store_true', help='Suppress verbose output, only show basic information in CSV format. Speeds listed in bit/s and not affected by --bytes')
        parser.add_argument('--csv-delimiter', default=',', type=str, help='Single character delimiter to use in CSV output. Default "%(default)s"')
        parser.add_argument('--csv-header', action='store_true', help='Print CSV headers')
        parser.add_argument('--json', action='store_true', help='Suppress verbose output, only show basic information in JSON format. Speeds listed in bit/s and not affected by --bytes')
        parser.add_argument('--list', action='store_true', help='Display a list of speedtest.net servers sorted by distance')
        parser.add_argument('--server', action='append', type=int, help='Specify a server ID to test against. Can be supplied multiple times')
        parser.add_argument('--exclude', action='append', type=int, help='Exclude a server from selection. Can be supplied multiple times')
        parser.add_argument('--mini', help='URL of the Speedtest Mini server')
        parser.add_argument('--source', help='Source IP address to bind to')
        parser.add_argument('--timeout', default=10.0, type=float, help='HTTP timeout in seconds. Default %(default)s')
        parser.add_argument('--secure', action='store_true', help='Use HTTPS instead of HTTP when communicating with speedtest.net operated servers')
        parser.add_argument('--no-pre-allocate', action='store_false', dest='pre_allocate', help='Do not pre allocate upload data. Pre allocation is enabled by default to improve upload performance. To support systems with insufficient memory, use this option to avoid a MemoryError')
        parser.add_argument('--debug', action='store_true', help=argparse.SUPPRESS, default=argparse.SUPPRESS)
        self.args = parser.parse_args(['--version'])

def main():
    option = Option()
    if option.args.version:
        print('%s %s' % (option.prog, speedtest.__version__, ))
        print('Python %s' % (sys.version.strip(), ))
        return

    testsuite = speedtest.TestSuite()
    if option.args.list:
        for server in sorted(testsuite.servers, key=lambda server: server.distance):
            print('%(id)5d) %(sponsor)s (%(name)s, %(country)s) [%(distance)0.2fkm]' % {
                'id': server.id,
                'sponsor': server.sponsor,
                'name': server.name,
                'country': server.country,
                'distance': server.distance, })
    if option.args.download:
        print('Download: %s%s/s' % (
            units.Bandwidth(testsuite.results.download.speed) / option.args.units[1],
            option.args.units[0], ))
    if option.args.upload:
        print('Upload: %s%s/s' % (
            units.Bandwidth(testsuite.results.upload.speed) / option.args.units[1],
            option.args.units[0], ))
    if option.args.simple:
        print('Ping: %fms\nDownload: %s%s/s\nUpload: %s%s/s' % (
            testsuite.results.server.latency,
            units.Bandwidth(testsuite.results.download.speed) / option.args.units[1],
            option.args.units[0],
            units.Bandwidth(testsuite.results.upload.speed) / option.args.units[1],
            option.args.units[0], ))
    elif option.args.csv:
        print(testsuite.results.csv())
    elif option.args.json:
        print(testsuite.results.json())

if __name__ == '__main__':
    main()