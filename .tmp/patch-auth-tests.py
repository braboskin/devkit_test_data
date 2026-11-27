import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\tests\test_app_auth.py")
s = p.read_text(encoding="utf-8")
anchor = "    def test_me_requires_session(self) -> None:"
assert anchor in s
tests = '''    def test_change_password_flow(self) -> None:
        alice = TestClient(self.app)
        self._login(alice, ALICE)
        changed = alice.post(
            "/api/auth/password",
            json={"old_password": ALICE["password"], "new_password": "new-alice-pass"},
        )
        self.assertEqual(changed.status_code, 204, changed.text)
        # Текущая сессия продолжает работать.
        self.assertEqual(alice.get("/api/me").status_code, 200)
        alice.post("/api/auth/logout")
        old = alice.post("/api/auth/login", json=ALICE)
        self.assertEqual(old.status_code, 401, old.text)
        new = alice.post(
            "/api/auth/login",
            json={"username": ALICE["username"], "password": "new-alice-pass"},
        )
        self.assertEqual(new.status_code, 200, new.text)

    def test_change_password_validation(self) -> None:
        alice = TestClient(self.app)
        self._login(alice, ALICE)
        wrong = alice.post(
            "/api/auth/password",
            json={"old_password": "nope", "new_password": "new-alice-pass"},
        )
        self.assertEqual(wrong.status_code, 400, wrong.text)
        same = alice.post(
            "/api/auth/password",
            json={"old_password": ALICE["password"], "new_password": ALICE["password"]},
        )
        self.assertEqual(same.status_code, 422, same.text)
        short = alice.post(
            "/api/auth/password",
            json={"old_password": ALICE["password"], "new_password": "short"},
        )
        self.assertEqual(short.status_code, 422, short.text)
        anonymous = TestClient(self.app).post(
            "/api/auth/password",
            json={"old_password": ALICE["password"], "new_password": "new-alice-pass"},
        )
        self.assertEqual(anonymous.status_code, 401, anonymous.text)

'''
s = s.replace(anchor, tests + anchor, 1)
p.write_text(s, encoding="utf-8")
print("auth tests added")
