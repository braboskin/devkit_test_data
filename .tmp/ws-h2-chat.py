import pathlib

path = pathlib.Path("repo/atlas/viewer/src/pages/chat/ui/Chat.tsx")
text = path.read_text(encoding="utf-8")

# 1. styled-импорт и новые примитивы.
old_react = "import { useCallback, useRef, useState } from 'react';"
new_react = "import styled from '@emotion/styled';\nimport { useCallback, useRef, useState } from 'react';"
assert old_react in text
text = text.replace(old_react, new_react, 1)

old_ui = """import {
  Badge,
  Button,
  Empty,
  ErrorNote,
  Loading,
  Note,
  TextAreaField,
  useAction,
  useResource,
} from '../../../shared/ui';"""
new_ui = """import {
  Badge,
  Button,
  EmptyState,
  ErrorNote,
  Loading,
  m,
  Note,
  PageFrame,
  PageHeader,
  Panel,
  SelectField,
  TextAreaField,
  useAction,
  useResource,
} from '../../../shared/ui';"""
assert old_ui in text
text = text.replace(old_ui, new_ui, 1)

# 2. Стили: вставляем перед компонентом чата.
styles = """
const ChatLayout = styled.div`
  display: grid;
  grid-template-columns: minmax(260px, 300px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  min-height: 0;

  @media (max-width: 960px) {
    grid-template-columns: minmax(0, 1fr);
  }
`;

const Column = styled(Panel)`
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  max-height: calc(100vh - 220px);
  padding: 16px;
  overflow: hidden;
`;

const Row = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: flex-end;
`;

const Muted = styled.p`
  margin: 0;
  color: var(--muted);
  font-size: 13px;
`;

const AlertBlock = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent);
  border-radius: 12px;
  background: color-mix(in srgb, var(--danger) 12%, var(--surface));
  color: var(--text);
  font-size: 13.5px;
`;

const ChatList = styled.ul`
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-y: auto;
`;

const ChatItem = styled.button<{ $active: boolean }>`
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid
    ${({ $active }) => ($active ? 'var(--accent)' : 'transparent')};
  border-radius: 10px;
  background: ${({ $active }) => ($active ? 'var(--accent-soft)' : 'transparent')};
  color: var(--text);
  text-align: left;
  cursor: pointer;

  &:hover {
    background: var(--hover);
  }

  strong {
    font-size: 13.5px;
    font-weight: 500;
  }

  small {
    color: var(--muted);
    font-size: 11.5px;
  }
`;

const Proposals = styled.section`
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  overflow-y: auto;
  border-top: 1px solid var(--border);
  padding-top: 12px;

  h3 {
    margin: 0;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--faint);
  }
`;

const ProposalCard = styled.article`
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--sunken);

  p {
    margin: 0;
    font-size: 13px;
  }

  pre {
    margin: 0;
    max-height: 180px;
    overflow: auto;
    font-size: 12px;
    color: var(--muted);
  }
`;

const Thread = styled(Column)`
  max-height: calc(100vh - 220px);
  padding: 0;
  gap: 0;
`;

const Messages = styled.ol`
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  padding: 16px;
  overflow-y: auto;
  list-style: none;
`;

const Message = styled(m.li)<{ $own: boolean }>`
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 78%;
  align-self: ${({ $own }) => ($own ? 'flex-end' : 'flex-start')};
  align-items: ${({ $own }) => ($own ? 'flex-end' : 'flex-start')};
`;

const MessageMeta = styled.span`
  font-size: 11.5px;
  color: var(--faint);
`;

const Bubble = styled.div<{ $own: boolean }>`
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid
    ${({ $own }) =>
      $own ? 'color-mix(in srgb, var(--accent) 35%, transparent)' : 'var(--border)'};
  border-radius: ${({ $own }) =>
    $own ? '14px 4px 14px 14px' : '4px 14px 14px 14px'};
  background: ${({ $own }) =>
    $own
      ? 'color-mix(in srgb, var(--accent) 14%, var(--surface))'
      : 'var(--raised)'};
  color: var(--text);
  font-size: 13.5px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
`;

const Citations = styled.ul`
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0 0 0 12px;
  list-style: none;
  border-left: 2px solid var(--border);

  li {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 12px;
    color: var(--muted);
  }

  strong {
    color: var(--text);
    font-weight: 500;
  }
`;

const Status = styled.p`
  margin: 0;
  min-height: 16px;
  font-size: 12px;
  color: var(--faint);
`;

const UsageLine = styled.p`
  margin: 0;
  padding: 0 16px 8px;
  font-size: 11.5px;
  color: var(--faint);
  font-variant-numeric: tabular-nums;
`;

const Trace = styled.details`
  margin: 0 16px 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--sunken);
  font-size: 12.5px;

  summary {
    cursor: pointer;
    color: var(--muted);
  }

  div {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-top: 8px;
  }

  strong {
    font-weight: 500;
  }

  pre {
    margin: 0;
    max-height: 240px;
    overflow: auto;
    color: var(--muted);
    font-size: 12px;
  }
`;

const Composer = styled.form`
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 16px 16px;
  border-top: 1px solid var(--border);

  &:focus-within {
    border-top-color: color-mix(in srgb, var(--accent) 50%, var(--border));
  }
`;

function enter(index: number) {
  return {
    initial: { opacity: 0, y: 6 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.18, delay: Math.min(index, 8) * 0.03 },
  };
}

"""

marker = "export default function ChatPage({"
assert marker in text
text = text.replace(marker, styles + marker, 1)

# 3. JSX: отрезаем старый return и пишем новый.
return_marker = '  return (\n    <div className="chat-layout">'
index = text.index(return_marker)
head = text[:index]

jsx = """  return (
    <PageFrame>
      <PageHeader
        title="Чат"
        description={
          activeAgent
            ? `Агент «${activeAgent.name}»${activeAgent.model ? ` · ${activeAgent.model}` : ''}`
            : 'Диалоги с агентом и предложения, которые ждут решения'
        }
      />
      {sendError !== null ? (
        <AlertBlock role="alert">
          <span>{sendError}</span>
          <Button onClick={onGoSettings}>Открыть настройки</Button>
        </AlertBlock>
      ) : null}

      <ChatLayout>
        <Column aria-label="Диалоги">
          <Row>
            <SelectField
              label="Агент для нового чата"
              value={agentId ?? undefined}
              options={(agents.data ?? []).map((agent) => ({
                value: agent.id,
                label: agent.name,
              }))}
              onChange={(next) => {
                const value = Array.isArray(next) ? next[0] : next;
                if (value !== undefined) {
                  setAgentId(Number(value));
                }
              }}
            />
            <Button onClick={() => void createChat()}>Новый чат</Button>
          </Row>
          <ErrorNote error={agents.error ?? chats.error} />
          {chats.loading && chats.data === null ? <Loading /> : null}
          {chats.data !== null && chats.data.length === 0 ? (
            <EmptyState
              title="Чатов пока нет"
              hint="Создайте первый диалог кнопкой «Новый чат»."
            />
          ) : null}

          <ChatList aria-label="Список чатов">
            {(chats.data ?? []).map((chat) => (
              <li key={chat.id}>
                <ChatItem
                  type="button"
                  $active={chat.id === activeId}
                  aria-current={chat.id === activeId ? 'page' : undefined}
                  onClick={() => {
                    setActiveId(chat.id);
                    setSendError(null);
                  }}
                >
                  <strong>{chat.title ?? `Чат #${chat.id}`}</strong>
                  <small>{chat.agent_name ?? 'агент'}</small>
                </ChatItem>
              </li>
            ))}
          </ChatList>

          {proposals.data && proposals.data.length > 0 ? (
            <Proposals aria-labelledby="pending-heading">
              <h3 id="pending-heading">Ждут решения</h3>
              {proposals.data.map((proposal) => (
                <ProposalCard key={proposal.id}>
                  <Badge
                    label={KIND_LABELS[proposal.kind] ?? proposal.kind}
                    tone={DESTRUCTIVE.has(proposal.kind) ? 'warn' : 'info'}
                  />
                  {proposal.kind === ACCESS_KIND ? (
                    <p>{accessDescription(proposal.payload)}</p>
                  ) : (
                    <pre>{JSON.stringify(proposal.payload, null, 2)}</pre>
                  )}
                  <Row>
                    <Button
                      disabled={actions.busy}
                      onClick={() => void apply(proposal)}
                    >
                      {proposal.kind === ACCESS_KIND ? 'Разрешить' : 'Применить'}
                    </Button>
                    <Button
                      disabled={actions.busy}
                      onClick={() => void reject(proposal)}
                    >
                      Отменить
                    </Button>
                  </Row>
                </ProposalCard>
              ))}
              <ErrorNote error={actions.error} />
              <Note note={actions.note} />
            </Proposals>
          ) : null}
        </Column>

        <Thread aria-label="Сообщения">
          {activeId === null ? (
            <EmptyState
              title="Выберите чат"
              hint="Список диалогов — в панели слева."
            />
          ) : messages.loading && messages.data === null ? (
            <Loading />
          ) : (
            <>
              <ErrorNote error={messages.error} />
              <Messages aria-label="Лента сообщений">
                {(messages.data ?? []).map((message, index) => (
                  <Message
                    key={message.id}
                    $own={message.role === 'user'}
                    {...enter(index)}
                  >
                    <MessageMeta>
                      {message.role === 'user'
                        ? 'Вы'
                        : (activeAgent?.name ?? 'Агент')}
                    </MessageMeta>
                    <Bubble $own={message.role === 'user'}>
                      {message.content}
                      {message.status !== 'complete' ? (
                        <Badge
                          label={
                            message.status === 'cancelled'
                              ? 'Отменено'
                              : 'Ошибка'
                          }
                          tone={
                            message.status === 'cancelled'
                              ? 'neutral'
                              : 'danger'
                          }
                        />
                      ) : null}
                    </Bubble>
                    {message.citations.length > 0 ? (
                      <Citations aria-label="Источники">
                        {message.citations.map((citation, citationIndex) => (
                          <li key={`${message.id}-${citationIndex}`}>
                            <strong>
                              {citation.title ??
                                `Документ #${citation.document_id}`}
                            </strong>
                            <span>{citation.text}</span>
                          </li>
                        ))}
                      </Citations>
                    ) : null}
                  </Message>
                ))}

                {pendingUser !== null ? (
                  <Message $own {...enter(0)}>
                    <MessageMeta>Вы</MessageMeta>
                    <Bubble $own>{pendingUser}</Bubble>
                  </Message>
                ) : null}

                {stream.running || stream.text !== '' ? (
                  <Message $own={false} {...enter(0)}>
                    <MessageMeta>{activeAgent?.name ?? 'Агент'}</MessageMeta>
                    <Bubble $own={false}>
                      {stream.text || '…'}
                      {stream.running ? (
                        <Button onClick={() => void cancelStream()}>
                          Отменить
                        </Button>
                      ) : null}
                    </Bubble>
                    <Status role="status" aria-live="polite">
                      {stream.running ? 'Агент отвечает…' : ''}
                    </Status>
                    {stream.citations.length > 0 ? (
                      <Citations aria-label="Источники">
                        {stream.citations.map((citation, index) => (
                          <li key={index}>
                            <strong>{citation.title ?? 'Документ'}</strong>
                            <span>{citation.text}</span>
                          </li>
                        ))}
                      </Citations>
                    ) : null}
                    {stream.proposals.length > 0 ? (
                      <Row>
                        {stream.proposals.map((proposal) => (
                          <Button
                            key={proposal.id}
                            onClick={() => void apply(proposal)}
                          >
                            {proposal.kind === ACCESS_KIND
                              ? 'Разрешить доступ'
                              : `Применить: ${
                                  KIND_LABELS[proposal.kind] ?? proposal.kind
                                }`}
                          </Button>
                        ))}
                      </Row>
                    ) : null}
                  </Message>
                ) : null}
              </Messages>

              {lastUsage !== null ? (
                <UsageLine>
                  Токены: {lastUsage.prompt_tokens} вх /{' '}
                  {lastUsage.completion_tokens} исх
                  {usageCost
                    ? ` · ≈ $${usageCost.usd.toFixed(4)} — ${usageCost.note}`
                    : ' · модель не из тарифа DeepSeek, стоимость не считаем'}
                  {activeAgent?.use_critic || activeAgent?.use_editor
                    ? ' · с учётом вызовов «Критика/Редактора»'
                    : ''}
                </UsageLine>
              ) : null}

              {trace.data && trace.data.length > 0 ? (
                <Trace>
                  <summary>Трейс сабагентов ({trace.data.length})</summary>
                  {trace.data.map((call) => (
                    <div key={call.id}>
                      <strong>
                        {call.child_name} → {call.parent_name}
                      </strong>
                      <pre>{call.output}</pre>
                    </div>
                  ))}
                </Trace>
              ) : null}
            </>
          )}

          <Composer onSubmit={(event) => void send(event)}>
            <TextAreaField
              label="Сообщение"
              id="chat-input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              rows={3}
              maxLength={8000}
              placeholder={
                activeAgent
                  ? `Спросить «${activeAgent.name}»…`
                  : 'Спросить агента…'
              }
            />
            <Row>
              <Button
                htmlType="submit"
                disabled={
                  input.trim() === '' || stream.running || activeId === null
                }
              >
                Отправить
              </Button>
              {activeAgent?.use_critic || activeAgent?.use_editor ? (
                <Muted>
                  Ответ проверяется сабагентами «Критик»/«Редактор» — чуть
                  медленнее.
                </Muted>
              ) : null}
            </Row>
          </Composer>
        </Thread>
      </ChatLayout>
    </PageFrame>
  );
}
"""

path.write_text(head + jsx, encoding="utf-8")
print("Chat.tsx rewritten:", len(head + jsx), "chars")
