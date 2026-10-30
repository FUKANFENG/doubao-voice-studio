"""Local account management uses synthetic credentials and never opens a window."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import auth_api


class AuthManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'auth.json'
        self.original = {'cookie': 'sessionid=old', 'web_id': 'web', 'tea_uuid': 'tea',
                         'proxy': 'http://127.0.0.1:7897'}
        self.path.write_text(json.dumps(self.original), encoding='utf-8')
        self.peer = '127.0.0.1'
        app = FastAPI()
        app.include_router(auth_api.router)

        @app.middleware('http')
        async def client_address(request, call_next):
            request.scope['client'] = (self.peer, 50000)
            return await call_next(request)

        self.client = TestClient(app, base_url='http://127.0.0.1:18088',
                                 headers={'X-Doubao-Local': '1'})
        self.addCleanup(self.client.close)
        self.patch_path = patch.object(auth_api, 'AUTH_PATH', self.path)
        self.patch_path.start()
        self.addCleanup(self.patch_path.stop)
        self.probe = patch.object(auth_api.auth_loader, '_probe_tts_handshake',
                                  new_callable=AsyncMock, return_value=(True, ''))
        self.probe_mock = self.probe.start()
        self.addCleanup(self.probe.stop)
        self.activate = patch.object(auth_api.auth_loader, 'activate')
        self.activate_mock = self.activate.start()
        self.addCleanup(self.activate.stop)

    def test_import_validates_before_save_preserves_other_settings_and_hides_secrets(self):
        response = self.client.post('/api/auth/import', json={'config': {'cookie': 'sessionid=synthetic'}})
        self.assertEqual(response.status_code, 200, response.text)
        saved = json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(saved['cookie'], 'sessionid=synthetic')
        self.assertEqual(saved['proxy'], self.original['proxy'])
        self.assertEqual(saved['web_id'], 'web')
        self.assertNotIn('synthetic', response.text)
        self.activate_mock.assert_called_once()
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_probe_or_save_failure_retains_existing_account(self):
        before = self.path.read_bytes()
        self.probe_mock.return_value = (False, 'upstream echoed synthetic-secret')
        response = self.client.post('/api/auth/import', json={'config': {'cookie': 'new'}})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('synthetic-secret', response.text)
        self.assertEqual(self.path.read_bytes(), before)
        self.activate_mock.assert_not_called()
        self.probe_mock.return_value = (True, '')
        with patch.object(auth_api.exporter, 'save_config', side_effect=PermissionError('synthetic-secret')):
            response = self.client.post('/api/auth/import', json={'config': {'cookie': 'new'}})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('synthetic-secret', response.text)
        self.assertEqual(self.path.read_bytes(), before)
        self.activate_mock.assert_not_called()

    def test_network_host_origin_and_proxy_guards_run_before_reading_credentials(self):
        cases = [({'Host': 'doubao.example.com'}, '127.0.0.1'),
                 ({}, '192.168.1.3'), ({'Origin': 'https://evil.example'}, '127.0.0.1'),
                 ({'Origin': 'null'}, '127.0.0.1'), ({'CF-Connecting-IP': '203.0.113.1'}, '127.0.0.1'),
                 ({'X-Forwarded-For': '127.0.0.1'}, '127.0.0.1'),
                 ({'Forwarded': 'for=127.0.0.1'}, '127.0.0.1'),
                 ({'Sec-Fetch-Site': 'cross-site'}, '127.0.0.1'),
                 ({'X-Doubao-Local': ''}, '127.0.0.1')]
        with patch.object(auth_api.exporter, 'load_config') as load:
            for headers, peer in cases:
                with self.subTest(headers=headers, peer=peer):
                    self.peer = peer
                    response = self.client.post('/api/auth/import', json={'config': {}}, headers=headers)
                    self.assertEqual(response.status_code, 403)
            load.assert_not_called()

    def test_invalid_payloads_never_echo_or_write_credentials(self):
        before = self.path.read_bytes()
        payloads = [{'config': {'cookie': 'synthetic-secret\r\nInjected: yes'}},
                    {'config': {'cookie': ''}}, {'config': {'unexpected': 'synthetic-secret'}},
                    {'config': []}, {'config': {'overrides': []}}, []]
        for payload in payloads:
            response = self.client.post('/api/auth/import', json=payload)
            self.assertEqual(response.status_code, 400, response.text)
            self.assertNotIn('synthetic-secret', response.text)
        response = self.client.post('/api/auth/import', content='x' * 65537,
                                    headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.path.read_bytes(), before)
        self.probe_mock.assert_not_awaited()

    def test_windows_local_read_uses_fixed_user_profile_and_does_not_return_cookie(self):
        with patch.object(auth_api.sys, 'platform', 'win32'), \
             patch.dict(auth_api.os.environ, {'LOCALAPPDATA': str(self.root)}), \
             patch.object(auth_api.exporter, 'collect_cookies', return_value=('sessionid=synthetic', 1)) as collect:
            response = self.client.post('/api/auth/local', json={})
        self.assertEqual(response.status_code, 200, response.text)
        collect.assert_called_once_with(self.root / 'Doubao' / 'User Data', 'Default')
        self.assertNotIn('synthetic', response.text)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['cookie'], 'sessionid=synthetic')

    def test_status_and_download_expose_only_public_metadata(self):
        response = self.client.get('/api/auth/status')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['can_manage'])
        self.assertNotIn('sessionid', response.text)
        self.peer = '203.0.113.1'
        self.assertFalse(self.client.get('/api/auth/status').json()['can_manage'])
        with patch.object(auth_api, 'TOOL_PATH', self.root / 'DoubaoAuthTool.exe'):
            self.assertEqual(self.client.get('/api/auth/tool').status_code, 404)
            (self.root / 'DoubaoAuthTool.exe').write_bytes(b'MZsynthetic-test-program')
            response = self.client.get('/api/auth/tool')
            self.assertEqual(response.content, b'MZsynthetic-test-program')
            self.assertIn('attachment', response.headers['content-disposition'])


if __name__ == '__main__':
    unittest.main()
