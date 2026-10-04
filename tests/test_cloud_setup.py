import importlib.util, tempfile, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('cloud_setup',Path(__file__).resolve().parents[1]/'scripts/cloud_setup.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name).resolve()
    def tearDown(self): self.tmp.cleanup()
    def put(self,name,text='{}'): (self.root/name).write_text(text)
    def plan(self,dirs=None): return m.plan(self.root,dirs or ['.'])
    def test_empty(self): self.assertTrue(self.plan()[1])
    def test_escape(self): self.assertTrue(self.plan(['../'])[1])
    def test_invalid_json(self): self.put('package.json','{'); self.assertTrue(self.plan()[1])
    def test_nonobject_json(self): self.put('package.json','[]'); self.assertTrue(self.plan()[1])
    def test_missing_lock(self): self.put('package.json'); self.assertTrue(self.plan()[1])
    def test_npm(self):
        self.put('package.json'); self.put('package-lock.json')
        commands,errors=self.plan(); self.assertFalse(errors); self.assertEqual(commands[0][1],['npm','ci'])
    def test_pnpm(self):
        self.put('package.json'); self.put('pnpm-lock.yaml','')
        self.assertEqual(self.plan()[0][0][1],['pnpm','install','--frozen-lockfile'])
    def test_multiple_locks(self):
        self.put('package.json'); self.put('package-lock.json'); self.put('pnpm-lock.yaml','')
        self.assertTrue(self.plan()[1])
    def test_manager_mismatch(self):
        self.put('package.json','{"packageManager":"pnpm@10.0.0"}'); self.put('package-lock.json')
        self.assertTrue(self.plan()[1])
    def test_bad_manager_type(self):
        self.put('package.json','{"packageManager":123}'); self.put('package-lock.json')
        self.assertTrue(self.plan()[1])
    def test_yarn_requires_review(self):
        self.put('package.json'); self.put('yarn.lock',''); self.assertTrue(self.plan()[1])
    def test_rust_no_lock(self): self.put('Cargo.toml',''); self.assertTrue(self.plan()[1])
    def test_rust_locked(self):
        self.put('Cargo.toml',''); self.put('Cargo.lock','')
        self.assertEqual(self.plan()[0][0][1],['cargo','fetch','--locked'])
    def test_duplicate_directory(self):
        self.put('package.json'); self.put('package-lock.json')
        self.assertEqual(len(self.plan(['.','.'])[0]),1)
if __name__=='__main__': unittest.main()
