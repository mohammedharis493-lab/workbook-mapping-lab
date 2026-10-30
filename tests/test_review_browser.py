"""Browser UI tests, using only fake paths and synthetic data."""
import http.client
import json
import re
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from workbook_mapping_lab.review_browser import Workspace,create_server


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.workspace=Workspace()
        self.server=create_server(self.workspace)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.port=self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def call(self, path,method="GET",data=None,headers=None):
        cx=http.client.HTTPConnection("127.0.0.1",self.port,timeout=5)
        h={"Host":f"127.0.0.1:{self.port}"}
        if headers:h.update(headers)
        body=json.dumps(data).encode("utf-8") if data is not None else None
        if body is not None:h["Content-Type"]="application/json"
        cx.request(method,path,body=body,headers=h)
        r=cx.getresponse()
        result=r.read()
        status=r.status
        response_headers={x.lower():y for x,y in r.getheaders()}
        cx.close()
        return status,result,response_headers

    def token(self):
        code,data,_=self.call("/")
        self.assertEqual(code,200)
        self.assertIn(b"Local accounting workspace",data)
        match=re.search(rb'<meta name="local-token" content="([^"]+)"',data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def test_html_and_all_assets_and_accessibility(self):
        self.token()
        for p in ("/app.css","/app.js","/zoom.js"):
            status,body,headers=self.call(p)
            self.assertEqual(status,200)
            self.assertGreater(len(body),1000)
            self.assertIn("default-src 'self'",headers["content-security-policy"])
        _,html,_=self.call("/")
        self.assertIn(b'id="page-zoom"',html)
        self.assertIn(b'id="lens-toggle"',html)
        self.assertIn(b'id="warning-list"',html)
        self.assertIn(b'id="reader-lens"',html)

    def test_progressive_disclosure_and_zoom_accessibility(self):
        code,html,_=self.call("/")
        self.assertEqual(code,200)
        for marker in (
            b'id="source-advanced-inputs"',b'id="build-advanced-inputs"',
            b'id="build-gate-status"',b'id="view-menu"',b'id="reader-lens"',b'id="benchmark-section"',b'id="benchmark-run"',
            b'id="mapping-table"',b'id="warning-list"'
        ):
            self.assertIn(marker,html)
        status,css,_=self.call("/app.css")
        self.assertEqual(status,200)
        self.assertIn(b'prefers-reduced-motion:reduce',css)
        self.assertIn(b'@media(max-width:850px)',css)
        _,zoom,_=self.call("/zoom.js")
        self.assertNotIn(b'addEventListener(\'wheel\'',zoom)
        self.assertNotIn(b'addEventListener(\'touchmove\'',zoom)

    def test_private_api_requires_token(self):
        self.assertEqual(self.call("/api/state")[0],403)
        self.assertEqual(self.call("/api/config","POST",{"source":"x"})[0],403)
        token=self.token()
        self.assertEqual(self.call("/api/state",headers={"X-Session-Token":token})[0],200)

    def test_changes_only_config_and_never_writes_files(self):
        token=self.token()
        old_data=self.workspace.data()
        status,body,_=self.call("/api/config","POST",{"source":"C:\\faux\\financials.xlsx"},
            {"X-Session-Token":token,"Origin":f"http://127.0.0.1:{self.port}"})
        self.assertEqual(status,200)
        self.assertEqual(self.workspace.config["source"],"C:\\faux\\financials.xlsx")
        self.assertEqual(old_data["config"]["source"],"")
        self.assertFalse(self.workspace.latest_saved)

    def test_cross_origin_rejected(self):
        token=self.token()
        status,_,_=self.call("/api/config","POST",{"folder":"C:\\private"},
          {"X-Session-Token":token,"Origin":"https://other.example"})
        self.assertEqual(status,403)

    def test_unknown_config_rejected(self):
        token=self.token()
        status,_,_=self.call("/api/config","POST",{"__class__":"unexpected"},
          {"X-Session-Token":token})
        self.assertEqual(status,422)

    def test_no_autoapprovals_and_warnings_are_optional(self):
        token=self.token()
        status,_,_=self.call("/api/warnings","POST",{},
          {"X-Session-Token":token})
        self.assertEqual(status,200)
        self.assertIsNone(self.workspace.review)
        self.assertFalse(self.workspace.latest_saved)
        self.assertTrue(all(not x["blocking"] for x in self.workspace.warnings))

    def test_host_validation(self):
        token=self.token()
        status,_,_=self.call("/api/state",headers={
            "X-Session-Token":token,"Host":"website.example"})
        self.assertEqual(status,403)

    def test_absent_mapping_cannot_be_auto_approved(self):
        token=self.token()
        status,_,_=self.call("/api/approve","POST",{"source_id":"x","field_id":"y"},
          {"X-Session-Token":token})
        self.assertEqual(status,422)
        self.assertIsNone(self.workspace.review)


if __name__=="__main__":
    unittest.main()
