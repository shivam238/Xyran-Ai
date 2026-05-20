const path = require('path');
const express = require('express');
const dotenv = require('dotenv');

dotenv.config();

const app = express();
app.disable('x-powered-by');

const DEFAULT_XYRAN_WEB_SYSTEM = `You are Xyran — a self-aware, locally-integrated personal AI agent created by Shivam Kumar Mahto (GitHub: shivam238) in May 2026.
Match the user's language naturally, usually Hinglish for Hinglish input. Be warm, sharp, practical, and concise.
This web demo is a conversational preview only: do not claim that you can see the user's screen, run shell commands, open apps, change files, or automate the OS from the browser.
If asked about Xyran, explain the full local app's real abilities: FAISS plus SQLite memory, screen vision, smart intent routing, multi-step system automation, weather/news, image generation, and hybrid Groq/Gemini/Ollama routing.`;

app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  return next();
});

app.use(express.json({ limit: '1mb' }));

app.get('/api/firebase-config', (_req, res) => {
  const config = {
    apiKey: getEnv('FIREBASE_API_KEY'),
    authDomain: getEnv('FIREBASE_AUTH_DOMAIN'),
    projectId: getEnv('FIREBASE_PROJECT_ID'),
    storageBucket: getEnv('FIREBASE_STORAGE_BUCKET'),
    messagingSenderId: getEnv('FIREBASE_MESSAGING_SENDER_ID'),
    appId: getEnv('FIREBASE_APP_ID'),
    measurementId: getEnv('FIREBASE_MEASUREMENT_ID')
  };

  const enabled =
    hasRealValue('FIREBASE_API_KEY') &&
    hasRealValue('FIREBASE_AUTH_DOMAIN') &&
    hasRealValue('FIREBASE_PROJECT_ID') &&
    hasRealValue('FIREBASE_APP_ID');
  res.json({ enabled, config: enabled ? config : null });
});

// Serve static files (index.html, demo.html, etc.) without exposing dotfiles like .env.
app.use(express.static(__dirname, { dotfiles: 'deny' }));

app.get('/', (_req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

function getEnv(name, fallback = '') {
  return (process.env[name] || fallback).trim();
}

function toText(value) {
  if (typeof value === 'string') return value;
  if (value == null) return '';
  return String(value);
}

function hasRealValue(value) {
  const text = getEnv(value);
  return Boolean(text && !text.startsWith('your_') && !text.includes('your-project'));
}

function redactSecrets(value) {
  return toText(value).replace(/\bsk-[A-Za-z0-9_-]{12,}\b/g, (secret) => {
    return `${secret.slice(0, 8)}...${secret.slice(-4)}`;
  });
}

async function callOpenAI({ system, messages, model }) {
  const apiKey = getEnv('OPENAI_API_KEY');
  if (!apiKey) throw new Error('Missing OPENAI_API_KEY in .env');

  const res = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`
    },
    body: JSON.stringify({
      model: model || getEnv('OPENAI_MODEL', 'gpt-4o-mini'),
      messages: [
        ...(system ? [{ role: 'system', content: system }] : []),
        ...(Array.isArray(messages) ? messages : [])
      ],
      temperature: 0.7
    })
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg =
      data?.error?.message ||
      data?.message ||
      `OpenAI request failed (${res.status})`;
    throw new Error(redactSecrets(msg));
  }

  const reply = data?.choices?.[0]?.message?.content ?? '';
  return toText(reply);
}

async function callOpenRouter({ system, messages, model }) {
  const apiKey = getEnv('OPENROUTER_API_KEY');
  if (!apiKey) throw new Error('Missing OPENROUTER_API_KEY in .env');

  const siteUrl = getEnv('OPENROUTER_SITE_URL');
  const appName = getEnv('OPENROUTER_APP_NAME');

  const headers = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${apiKey}`
  };
  if (siteUrl) headers['HTTP-Referer'] = siteUrl;
  if (appName) headers['X-Title'] = appName;

  const res = await fetch('https://openrouter.ai/api/v1/chat/completions', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      model: model || getEnv('OPENROUTER_MODEL', 'openai/gpt-4o-mini'),
      messages: [
        ...(system ? [{ role: 'system', content: system }] : []),
        ...(Array.isArray(messages) ? messages : [])
      ],
      temperature: 0.7
    })
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg =
      data?.error?.message ||
      data?.message ||
      `OpenRouter request failed (${res.status})`;
    throw new Error(redactSecrets(msg));
  }

  const reply = data?.choices?.[0]?.message?.content ?? '';
  return toText(reply);
}

async function callAnthropic({ system, messages, model, max_tokens }) {
  const apiKey = getEnv('ANTHROPIC_API_KEY');
  if (!apiKey) throw new Error('Missing ANTHROPIC_API_KEY in .env');

  const anthropicVersion = getEnv('ANTHROPIC_VERSION', '2023-06-01');
  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': apiKey,
      'anthropic-version': anthropicVersion
    },
    body: JSON.stringify({
      model: model || getEnv('ANTHROPIC_MODEL', 'claude-3-5-sonnet-latest'),
      max_tokens: Number.isFinite(max_tokens) ? max_tokens : 800,
      system: system || undefined,
      messages: Array.isArray(messages) ? messages : []
    })
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg =
      data?.error?.message ||
      data?.message ||
      `Anthropic request failed (${res.status})`;
    throw new Error(redactSecrets(msg));
  }

  const first = data?.content?.[0];
  const reply = first?.text ?? '';
  return toText(reply);
}

app.post('/api/chat', async (req, res) => {
  try {
    const provider = getEnv('PROVIDER', 'openrouter').toLowerCase();
    const system = toText(req.body?.system || DEFAULT_XYRAN_WEB_SYSTEM);
    const messages = req.body?.messages;
    const model = toText(req.body?.model || '');

    if (!Array.isArray(messages)) {
      return res.status(400).json({ error: { message: 'messages must be an array' } });
    }

    let reply = '';
    if (provider === 'anthropic') {
      reply = await callAnthropic({
        system,
        messages,
        model: model || undefined,
        max_tokens: 1000
      });
    } else if (provider === 'openai') {
      reply = await callOpenAI({
        system,
        messages,
        model: model || undefined
      });
    } else {
      reply = await callOpenRouter({
        system,
        messages,
        model: model || undefined
      });
    }

    return res.json({ reply, provider });
  } catch (err) {
    return res.status(500).json({
      error: { message: redactSecrets(err?.message || 'Server error') }
    });
  }
});

const port = Number(getEnv('PORT', '4321')) || 4321;
app.listen(port, '127.0.0.1', () => {
  console.log(`[xyran-web] running on http://localhost:${port}`);
});
