"""Participant-only chat, unread accounting, attachments, and event stream boundaries."""

import pytest


@pytest.mark.parametrize('length,status', [(0, 422), (1, 201), (2000, 201), (2001, 422)])
def test_message_length_boundaries(api, headers, accepted_chat, db, length, status):
    """OpenAPI ChatMessageCreate: content length 1..2000; odd/tasks/caja-negra.md S3 boundary partitioning."""
    response = api.post(f"/api/chats/{accepted_chat['chat']}/messages", headers=headers(), json={'content': 'x' * length})
    assert response.status_code == status, response.text
    assert db.execute('SELECT count(*) FROM "Mensajes"').fetchone()[0] == (1 if status == 201 else 0)


@pytest.mark.parametrize('actor', ['other', 'outsider', 'driver'])
def test_chat_participant_idor(api, headers, accepted_chat, db, actor):
    """README.md#chat-attachments-private-supabase-storage-bucket; odd/tasks/caja-negra.md S3 participant IDOR."""
    base = f"/api/chats/{accepted_chat['chat']}"
    assert api.get(base + '/messages', headers=headers(actor)).status_code == 404
    assert api.post(base + '/messages', headers=headers(actor), json={'content': 'Hello'}).status_code == 404
    assert api.post(base + '/read', headers=headers(actor)).status_code == 404
    assert db.execute('SELECT count(*) FROM "Mensajes"').fetchone()[0] == 0


def test_timeline_and_unread_read_transition(api, headers, accepted_chat, quote_body):
    """odd/tasks/chat-completion.md S1, S4: flat timeline, own messages/quotes excluded, mark read returns 204."""
    chat_id = accepted_chat['chat']
    base = f'/api/chats/{chat_id}'
    assert api.get('/api/chats/unread', headers=headers()).json() == {'total': 0}
    message = api.post(base + '/messages', headers=headers('owner'), json={'content': 'Cargo is ready'})
    assert message.status_code == 201
    assert message.json()['fromMe'] is True
    assert api.post(base + '/quotations', headers=headers('owner'), json=quote_body).status_code == 201
    assert api.get('/api/chats/unread', headers=headers()).json() == {'total': 1}
    assert api.get('/api/chats/unread', headers=headers('owner')).json() == {'total': 0}
    page = api.get(base + '/messages', headers=headers()).json()
    assert 'chat' not in page and 'hasMore' not in page
    assert page['viewerRole'] == 'customer' and page['chatId'] == chat_id
    assert {entry['kind'] for entry in page['timeline']} == {'message', 'quotation'}
    assert api.get('/api/chats', headers=headers()).json()['items'][0]['unreadCount'] == 1
    assert api.post(base + '/read', headers=headers()).status_code == 204
    assert api.get('/api/chats/unread', headers=headers()).json() == {'total': 0}
    assert api.post(base + '/read', headers=headers()).status_code == 204


@pytest.mark.parametrize('size,prefix,status', [(4, b'text', 415), (5 * 1024 * 1024, b'\x89PNG\r\n\x1a\n', 201), (5 * 1024 * 1024 + 1, b'\x89PNG\r\n\x1a\n', 413)])
def test_attachment_size_and_magic_type(api, headers, accepted_chat, db, size, prefix, status):
    """README.md#chat-attachments-private-supabase-storage-bucket: magic-byte MIME, 5 MiB limit."""
    data = prefix + b'\0' * max(0, size - len(prefix))
    base = f"/api/chats/{accepted_chat['chat']}/messages"
    response = api.post(base + '/attachments', headers=headers(), files={'photo': ('not-an-image.txt', data, 'text/plain')})
    assert response.status_code == status, response.text
    assert db.execute('SELECT count(*) FROM "Mensajes"').fetchone()[0] == (1 if status == 201 else 0)
    if status == 201:
        message_id = response.json()['messageId']
        assert response.json()['attachment'] == {'contentType': 'image/png', 'sizeBytes': size}
        assert api.get(base + f'/{message_id}/attachment', headers=headers('owner')).status_code == 200
        assert api.get(base + f'/{message_id}/attachment', headers=headers('other')).status_code == 404
        assert api.get('/api/chats', headers=headers('owner')).json()['items'][0]['lastMessage']['content'] == 'Foto'


def test_sse_token_is_never_read_from_url(api, token):
    """README.md#chat-real-time-events: Authorization required; JWT must not be accepted from URL."""
    response = api.get('/api/chats/events', params={'token': token()})
    assert response.status_code in (401, 403)


def test_sse_is_authenticated_event_stream(api, headers):
    """README.md#chat-real-time-events: authenticated per-user text/event-stream, ready/degraded state."""
    with api.stream('GET', '/api/chats/events', headers=headers()) as response:
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        lines = response.iter_lines()
        first = next(lines)
        assert first in ('event: ready', 'event: degraded'), first
