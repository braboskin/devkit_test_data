import pathlib
p = pathlib.Path(r"X:\devkit_projects\projects\atlas\repo\atlas\web\src\pages\settings\ui\Settings.tsx")
s = p.read_text(encoding="utf-8")

old = """  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let data: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(profileData);
      if (
        parsed === null ||
        typeof parsed !== 'object' ||
        Array.isArray(parsed)
      ) {
        throw new Error('not an object');
      }
      data = parsed as Record<string, unknown>;
    } catch {
      setProfileError('Профиль должен быть JSON-объектом.');
      return;
    }
    setProfileError(null);
    await profileActions.run(async () => {
      await api('/api/profile', {
        method: 'PUT',
        body: JSON.stringify({ data, summary: summary.trim() || null }),
      });
    }, 'Профиль сохранён.');
  }
"""

new = """  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    let data: Record<string, unknown> = {};
    try {
      const parsed: unknown = JSON.parse(profileData.trim() || '{}');
      if (
        parsed === null ||
        typeof parsed !== 'object' ||
        Array.isArray(parsed)
      ) {
        throw new Error('not an object');
      }
      data = parsed as Record<string, unknown>;
    } catch {
      setProfileError('Профиль должен быть JSON-объектом.');
      return;
    }
    setProfileError(null);
    // Типизированные поля главнее JSON-редактора: остальные ключи сохраняются.
    const merged = withPerson(data, person);
    await profileActions.run(async () => {
      await api('/api/profile', {
        method: 'PUT',
        body: JSON.stringify({ data: merged, summary: summary.trim() || null }),
      });
    }, 'Профиль сохранён.');
  }

  async function uploadPhoto(file: File) {
    await profileActions.run(async () => {
      await uploadAvatar(file);
    }, 'Фото обновлено.');
  }

  async function changePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fresh = newPassword.trim();
    if (fresh.length < 8) {
      setPasswordError('Новый пароль должен быть не короче 8 символов.');
      return;
    }
    if (fresh === oldPassword) {
      setPasswordError('Новый пароль должен отличаться от текущего.');
      return;
    }
    setPasswordError(null);
    await passwordAction.run(async () => {
      await api('/api/auth/password', {
        method: 'POST',
        body: JSON.stringify({ old_password: oldPassword, new_password: fresh }),
      });
    }, 'Пароль изменён.');
    setOldPassword('');
    setNewPassword('');
    setPasswordOpen(false);
  }
"""

assert old in s, "saveProfile block not found"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("profile save extended")
