import pathlib

p = pathlib.Path(
    r"X:\devkit_projects\projects\atlas\repo\atlas\web\src\pages\settings\ui\Settings.tsx"
)
s = p.read_text(encoding="utf-8")

start_marker = '        <Section aria-labelledby="profile-heading">'
start = s.index(start_marker)
end = s.index("</Section>", start) + len("</Section>")

new_block = '''        <Section aria-labelledby="profile-heading">
          <SectionTitle id="profile-heading">Профиль</SectionTitle>
          <ErrorNote
            error={
              profileActions.error ??
              profile.error ??
              profileError ??
              passwordAction.error
            }
          />
          <Note note={profileActions.note ?? passwordAction.note} />
          {profile.loading && profile.data === null ? (
            <Loading />
          ) : (
            <Form onSubmit={(event) => void saveProfile(event)}>
              <PersonRow>
                <Avatar
                  name={person.name || me.data?.username || 'Вы'}
                  src={avatarSrc(me.data?.avatar_ref)}
                  size="lg"
                />
                <div>
                  <Muted>Фото профиля</Muted>
                  <Row>
                    <Upload
                      accept="image/*"
                      showUploadList={false}
                      beforeUpload={(file) => {
                        if (!file.type.startsWith('image/')) {
                          profileActions.setError(
                            'Фото должно быть изображением.',
                          );
                          return false;
                        }
                        if (file.size > PHOTO_MAX_BYTES) {
                          profileActions.setError('Фото больше 10 МБ.');
                          return false;
                        }
                        void uploadPhoto(file);
                        return false;
                      }}
                    >
                      <Button variant="secondary" disabled={profileActions.busy}>
                        Загрузить фото
                      </Button>
                    </Upload>
                    <Muted>JPG или PNG, до 10 МБ.</Muted>
                  </Row>
                </div>
              </PersonRow>

              <FieldGrid>
                <TextField
                  label="Логин"
                  id="profile-login"
                  value={me.data?.username ?? ''}
                  readOnly
                  hint="Логин используется для входа и здесь не меняется."
                />
                <div>
                  <TextField
                    label="Пароль"
                    id="profile-password-placeholder"
                    value="••••••••"
                    readOnly
                    hint="Сменить пароль можно кнопкой ниже."
                  />
                </div>
                <TextField
                  label="Имя"
                  id="profile-name"
                  value={person.name}
                  maxLength={120}
                  onChange={(event) =>
                    setPerson((value) => ({ ...value, name: event.target.value }))
                  }
                  hint="Агент увидит имя в своём контексте."
                />
                <NumberField
                  label="Возраст"
                  id="profile-age"
                  min={14}
                  max={120}
                  step={1}
                  value={person.age}
                  onChange={(value) =>
                    setPerson((value_) => ({ ...value_, age: value }))
                  }
                  hint="От 14 до 120 лет."
                />
                <TextField
                  label="Город"
                  id="profile-city"
                  value={person.city}
                  maxLength={120}
                  onChange={(event) =>
                    setPerson((value) => ({ ...value, city: event.target.value }))
                  }
                />
                <TextField
                  label="Род деятельности"
                  id="profile-occupation"
                  value={person.occupation}
                  maxLength={120}
                  onChange={(event) =>
                    setPerson((value) => ({
                      ...value,
                      occupation: event.target.value,
                    }))
                  }
                />
              </FieldGrid>

              <TextAreaField
                label="Сводка профиля"
                id="profile-summary"
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                rows={3}
                maxLength={4000}
                hint="Передаётся агенту как «Профиль владельца»."
              />

              <Collapse
                items={[
                  {
                    key: 'profile-json',
                    label: 'Дополнительно: данные профиля (JSON)',
                    children: (
                      <TextAreaField
                        label="Данные профиля (JSON)"
                        id="profile-data"
                        value={profileData}
                        onChange={(event) => setProfileData(event.target.value)}
                        rows={8}
                        spellCheck={false}
                        hint="Свободный JSON: типизированные поля выше имеют приоритет."
                      />
                    ),
                  },
                ]}
              />

              <Row>
                <Button htmlType="submit" disabled={profileActions.busy}>
                  Сохранить профиль
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setPasswordError(null);
                    setPasswordOpen(true);
                  }}
                >
                  Изменить пароль
                </Button>
              </Row>
            </Form>
          )}
        </Section>

        <Modal
          open={passwordOpen}
          title="Изменить пароль"
          onClose={() => setPasswordOpen(false)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setPasswordOpen(false)}>
                Отмена
              </Button>
              <Button
                htmlType="submit"
                form="password-form"
                disabled={passwordAction.busy}
              >
                Сохранить пароль
              </Button>
            </>
          }
        >
          <Form id="password-form" onSubmit={(event) => void changePassword(event)}>
            <TextField
              label="Текущий пароль"
              id="password-old"
              type="password"
              value={oldPassword}
              onChange={(event) => setOldPassword(event.target.value)}
              autoComplete="current-password"
            />
            <TextField
              label="Новый пароль"
              id="password-new"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              autoComplete="new-password"
              hint="Минимум 8 символов, отличный от текущего."
              error={passwordError}
            />
          </Form>
        </Modal>'''

s = s[:start] + new_block + s[end:]
p.write_text(s, encoding="utf-8")
print("profile section replaced")
