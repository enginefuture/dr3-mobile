"""Actual two-process native sockets/control; no game, save, device or production service."""
import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / 'third_party/nxnative/dm/host'


class NativeLan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='dr3-lan-test-')
        cls.binary = Path(cls.temp.name) / 'probe'
        subprocess.run(['clang', '-std=c11', '-O1', '-g', '-fsanitize=address,undefined', '-Wall', '-Wextra',
                        '-I' + str(HOST), str(ROOT / 'tests/lan_native_probe.c'),
                        str(HOST / 'hle_lan_native.c'), str(HOST / 'hle_lan_socket.c'),
                        '-o', str(cls.binary)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_actual_csrng_hook_fills_guest_span_without_services(self):
        binary = Path(self.temp.name) / 'crypto-probe'
        subprocess.run(['clang', '-O1', '-g', '-fsanitize=address,undefined', '-Wall', '-Wextra',
                        '-I' + str(HOST), '-I' + str(HOST / 'gen/01001B300B9BE000'),
                        str(ROOT / 'tests/lan_crypto_probe.c'), str(HOST / 'hle_lan_native.c'),
                        str(HOST / 'hle_lan_socket.c'), '-o', str(binary)], check=True, capture_output=True)
        probe = subprocess.run([str(binary)], capture_output=True, text=True, timeout=5)
        self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
        self.assertIn('actual CSPRNG hook bounds and registration passed', probe.stdout)

    def test_two_process_room_and_socket_semantics(self):
        addresses = re.findall(r'inet ([0-9.]+) ', subprocess.check_output(['ifconfig', 'lo0'], text=True))
        secondary = next((ip for ip in addresses if ip != '127.0.0.1'), None)
        if not secondary:
            self.skipTest('Two existing loopback IPv4 addresses required; test does not change interfaces')
        env = dict(os.environ, DM_DR3_LAN='1', DM_LAN_BIND_IP=secondary, DM_LAN_PEER='127.0.0.1:9')
        server = subprocess.Popen([str(self.binary), 'host'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = server.stdout.readline()
            self.assertTrue(line, server.stderr.read() if server.poll() is not None else 'host produced no port')
            port = json.loads(line)['control_port']
            self.malformed_and_capacity_controls(port, secondary)
            env.update(DM_LAN_BIND_IP='127.0.0.1', DM_LAN_PEER=f'{secondary}:{port}')
            client = subprocess.run([str(self.binary), 'client'], env=env, capture_output=True, text=True, timeout=12)
            self.assertEqual(client.returncode, 0, client.stdout + client.stderr)
            stdout, stderr = server.communicate(timeout=5)
            self.assertEqual(server.returncode, 0, stdout + stderr)
            result = json.loads(stdout.strip().splitlines()[-1])
            self.assertEqual(result, dict(udp=1, tcp=1, departed=1, nodes=1))
        finally:
            if server.poll() is None:
                server.kill()
                server.communicate()

    def test_ldn_ap_to_station_transition_preserves_socket_ownership(self):
        addresses = re.findall(r'inet ([0-9.]+) ', subprocess.check_output(['ifconfig', 'lo0'], text=True))
        secondary = next((ip for ip in addresses if ip != '127.0.0.1'), None)
        if not secondary:
            self.skipTest('Two existing loopback IPv4 addresses required')
        env = dict(os.environ, DM_DR3_LAN='1', DM_LAN_BIND_IP=secondary, DM_LAN_PEER='127.0.0.1:9')
        server = subprocess.Popen([str(self.binary), 'host'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            port = json.loads(server.stdout.readline())['control_port']
            env.update(DM_LAN_BIND_IP='127.0.0.1', DM_LAN_PEER=f'{secondary}:{port}')
            client = subprocess.run([str(self.binary), 'transitionclient'], env=env, capture_output=True, text=True, timeout=12)
            self.assertEqual(client.returncode, 0, client.stdout + client.stderr)
            self.assertIn('LDN_TRANSITION_CLOSE_CREATE_FCNTL_BROADCAST_BIND passed', client.stdout)
            stdout, stderr = server.communicate(timeout=5)
            self.assertEqual(server.returncode, 0, stdout + stderr)
            self.assertEqual(json.loads(stdout.strip().splitlines()[-1]), dict(udp=1, tcp=1, departed=1, nodes=1))
        finally:
            if server.poll() is None:
                server.kill()
                server.communicate()

    def test_disabled_suspend_resume_and_reinitialize(self):
        env = dict(os.environ, DM_LAN_BIND_IP='127.0.0.1', DM_LAN_PEER='127.0.0.1:9')
        probe = subprocess.run([str(self.binary), 'lifecycle'], env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)

    def test_host_destroy_disconnects_an_existing_member(self):
        addresses = re.findall(r'inet ([0-9.]+) ', subprocess.check_output(['ifconfig', 'lo0'], text=True))
        secondary = next((ip for ip in addresses if ip != '127.0.0.1'), None)
        if not secondary:
            self.skipTest('Two existing loopback IPv4 addresses required')
        env = dict(os.environ, DM_DR3_LAN='1', DM_LAN_BIND_IP=secondary, DM_LAN_PEER='127.0.0.1:9')
        server = subprocess.Popen([str(self.binary), 'destroyhost'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            port = json.loads(server.stdout.readline())['control_port']
            env.update(DM_LAN_BIND_IP='127.0.0.1', DM_LAN_PEER=f'{secondary}:{port}')
            client = subprocess.run([str(self.binary), 'destroyclient'], env=env, capture_output=True, text=True, timeout=12)
            self.assertEqual(client.returncode, 0, client.stdout + client.stderr)
            stdout, stderr = server.communicate(timeout=5)
            self.assertEqual(server.returncode, 0, stdout + stderr)
            self.assertIn('"destroyed":true', stdout)
        finally:
            if server.poll() is None:
                server.kill()
                server.communicate()

    @unittest.skipUnless(os.environ.get('DM_LAN_BONJOUR_TEST') == '1', 'Opt-in Bonjour test advertises a temporary local service')
    def test_bonjour_discovers_without_manual_peer(self):
        ip = subprocess.check_output(['ipconfig', 'getifaddr', 'en0'], text=True).strip()
        self.assertTrue(ip)
        temporary = Path(self.temp.name)
        common = ['-O1', '-g', '-fsanitize=address,undefined', '-I' + str(HOST)]
        obj = temporary / 'probe-entry.o'
        subprocess.run(['clang', *common, '-Dmain=lan_probe_main', '-c', str(ROOT / 'tests/lan_native_probe.c'), '-o', str(obj)], check=True, capture_output=True)
        entry = temporary / 'entry.m'
        entry.write_text('#import <Foundation/Foundation.h>\nextern int lan_probe_main(int,char**);\nint main(int argc,char**argv){@autoreleasepool{return lan_probe_main(argc,argv);}}\n')
        binary = temporary / 'bonjour-probe'
        subprocess.run(['clang', *common, '-fobjc-arc', '-fblocks', str(entry), str(obj),
                        str(HOST / 'hle_lan_native.c'), str(HOST / 'hle_lan_socket.c'),
                        str(ROOT / 'native/lan_discovery_apple.m'), '-framework', 'Foundation', '-o', str(binary)],
                       check=True, capture_output=True)
        # Real game rooms use scene1; other isolated probes use scene7. A fresh
        # scene also prevents an independently running Bonjour suite from making
        # our exact-one-room assertion ambiguous.
        test_scene = 1000 + secrets.randbelow(64000)
        env = dict(os.environ, DM_DR3_LAN='1', DM_LAN_BIND_IP=ip, DM_LAN_TEST_SCENE=str(test_scene))
        env.pop('DM_LAN_PEER', None)
        server = subprocess.Popen([str(binary), 'host'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertTrue(server.stdout.readline())
            env['DM_LAN_BIND_IP'] = '127.0.0.1'
            client = subprocess.run([str(binary), 'client'], env=env, capture_output=True, text=True, timeout=20)
            if client.returncode:
                server.kill()
                hostout, hosterr = server.communicate()
                self.fail(client.stdout + client.stderr + '\nHOST: ' + hostout + hosterr)
            stdout, stderr = server.communicate(timeout=5)
            self.assertEqual(server.returncode, 0, stdout + stderr)
            self.assertIn('Bonjour room published', stderr)
        finally:
            if server.poll() is None:
                server.kill()
                server.communicate()

    def malformed_and_capacity_controls(self, port, host_ip):
        target = (host_ip, port)
        key = bytes([11]) * 32

        def packet(kind, identity, body=b'', room=bytes(16), nonce=1, signed=False):
            raw = b'DR3L' + struct.pack('!BBHQ', 1, kind, len(body), nonce) + room + struct.pack('!Q', identity) + body
            return raw + (hmac.new(key, raw, hashlib.sha256).digest() if signed else bytes(32))

        peers = []
        try:
            for number in range(2):
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.bind(('127.0.0.1', 0))
                s.settimeout(.2)
                peers.append(s)
            first = peers[0]
            for raw in (b'bad', b'DR3L' + bytes(2000), packet(99, 999), packet(3, 999, bytes(56)),
                        packet(1, 999)[:-1], packet(1, 999) + b'X'):
                first.sendto(raw, target)
            first.sendto(packet(1, 3), target)
            response = first.recv(1500)
            self.assertEqual(response[:6], b'DR3L\x01\x02')
            self.assertEqual(len(response), 40 + 0x480 + 32)
            room = response[16:32]
            # Correct authentication, but impossible roster/name and version inputs are rejected.
            first.sendto(packet(3, 3, b'X' * 48 + struct.pack('!H', 123) + bytes(6), room, signed=True), target)
            with self.assertRaises(socket.timeout):
                first.recv(1500)
            joined = []
            for i, s in enumerate(peers):
                identity = 100 + i
                body = (f'capacity-{i}'.encode() + bytes(48))[:48] + struct.pack('!H', 123) + bytes(6)
                s.sendto(packet(3, identity, body, room, nonce=identity, signed=True), target)
                if i == 0:
                    reply = s.recv(1500)
                    self.assertEqual(reply[5], 4)
                    self.assertEqual(reply[40 + 0x67], i + 2)
                    joined.append((s, identity))
                else:
                    with self.assertRaises(socket.timeout):
                        s.recv(1500)
            # A repeated authenticated JOIN from the same endpoint is idempotent.
            s, identity = joined[0]
            body = (b'capacity-0' + bytes(48))[:48] + struct.pack('!H', 123) + bytes(6)
            s.sendto(packet(3, identity, body, room, nonce=identity, signed=True), target)
            response = s.recv(1500)
            self.assertIn(response[5], (4, 6))
            self.assertEqual(response[40 + 0x67], 2)
            for s, identity in joined:
                s.sendto(packet(7, identity, room=room, signed=True), target)
            time.sleep(.12)
        finally:
            for s in peers:
                s.close()


if __name__ == '__main__':
    unittest.main()
