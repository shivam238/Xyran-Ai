const { onRequest } = require('firebase-functions/v2/https');
const { defineSecret } = require('firebase-functions/params');
const { buildXyranSystemPrompt, XYRAN_KNOWLEDGE } = require('./xyran-knowledge');

const OPENROUTER_API_KEY = defineSecret('OPENROUTER_API_KEY');
const OPENAI_API_KEY = defineSecret('OPENAI_API_KEY');
const ANTHROPIC_API_KEY = defineSecret('ANTHROPIC_API_KEY');

function toText(value) {
  if (typeof value === 'string') return value;
  if (value == null) return '';
  return String(value);
}

function redactSecrets(value) {
  return toText(value).replace(/\b(sk-|or-)[A-Za-z0-9_-]{12,}\b/g, (secret) => {
    return `${secret.slice(0, 8)}...${secret.slice(-4)}`;
  });
}

function sendJson(res, status, payload) {
  res.status(status).set('Content-Type', 'application/json').send(JSON.stringify(payload));
}

async function callOpenRouter({ system, messages, model }) {
  const apiKey = OPENROUTER_API_KEY.value();
  if (!apiKey) throw new Error('OPENROUTER_API_KEY secret is not configured');

  const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
      'HTTP-Referer': 'https://xyran-ai.web.app',
      'X-Title': 'Xyran Web'
    },
    body: JSON.stringify({
      model: model || process.env.OPENROUTER_MODEL || 'openai/gpt-4o-mini',
      messages: [
        ...(system ? [{ role: 'system', content: system }] : []),
        ...(Array.isArray(messages) ? messages : [])
      ],
      temperature: 0.7
    })
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const msg = data?.error?.message || data?.message || `OpenRouter request failed (${response.status})`;
    throw new Error(redactSecrets(msg));
  }

  return toText(data?.choices?.[0]?.message?.content ?? '');
}

async function callOpenAI({ system, messages, model }) {
  const apiKey = OPENAI_API_KEY.value();
  if (!apiKey) throw new Error('OPENAI_API_KEY secret is not configured');

  const response = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model: model || process.env.OPENAI_MODEL || 'gpt-4o-mini',
      messages: [
        ...(system ? [{ role: 'system', content: system }] : []),
        ...(Array.isArray(messages) ? messages : [])
      ],
      temperature: 0.7
    })
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const msg = data?.error?.message || data?.message || `OpenAI request failed (${response.status})`;
    throw new Error(redactSecrets(msg));
  }

  return toText(data?.choices?.[0]?.message?.content ?? '');
}

async function callAnthropic({ system, messages, model }) {
  const apiKey = ANTHROPIC_API_KEY.value();
  if (!apiKey) throw new Error('ANTHROPIC_API_KEY secret is not configured');

  const response = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': process.env.ANTHROPIC_VERSION || '2023-06-01'
    },
    body: JSON.stringify({
      model: model || process.env.ANTHROPIC_MODEL || 'claude-3-5-sonnet-latest',
      max_tokens: 1000,
      system: system || undefined,
      messages: Array.isArray(messages) ? messages : []
    })
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const msg = data?.error?.message || data?.message || `Anthropic request failed (${response.status})`;
    throw new Error(redactSecrets(msg));
  }

  return toText(data?.content?.[0]?.text ?? '');
}

exports.api = onRequest({
  cors: true,
  secrets: [OPENROUTER_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY]
}, async (req, res) => {
  try {
    if (req.method === 'OPTIONS') return res.status(204).send('');

    const pathname = new URL(req.url, 'https://xyran-ai.web.app').pathname;

    if (req.method === 'GET' && pathname.endsWith('/xyran-knowledge')) {
      return sendJson(res, 200, { name: 'Xyran AI', version: '1.0', knowledge: XYRAN_KNOWLEDGE.trim() });
    }

    if (req.method !== 'POST' || !pathname.endsWith('/chat')) {
      return sendJson(res, 404, { error: { message: 'Not found' } });
    }

    const messages = req.body?.messages;
    if (!Array.isArray(messages)) {
      return sendJson(res, 400, { error: { message: 'messages must be an array' } });
    }

    const provider = toText(req.body?.provider || process.env.PROVIDER || 'openrouter').toLowerCase();
    const system = buildXyranSystemPrompt(req.body?.system || '');
    const model = toText(req.body?.model || '');

    let reply = '';
    if (provider === 'openai') {
      reply = await callOpenAI({ system, messages, model });
    } else if (provider === 'anthropic') {
      reply = await callAnthropic({ system, messages, model });
    } else {
      reply = await callOpenRouter({ system, messages, model });
    }

    return sendJson(res, 200, { reply, provider });
  } catch (err) {
    return sendJson(res, 500, {
      error: { message: redactSecrets(err?.message || 'Server error') }
    });
  }
});
