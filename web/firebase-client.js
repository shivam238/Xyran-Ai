(function () {
  const state = {
    ready: false,
    disabled: false,
    initPromise: null,
    db: null,
    analytics: null,
    user: null,
    sessionId: getSessionId()
  };

  function getSessionId() {
    const key = 'xyranFirebaseSessionId';
    const existing = sessionStorage.getItem(key);
    if (existing) return existing;

    const id =
      (crypto.randomUUID && crypto.randomUUID()) ||
      `session_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    sessionStorage.setItem(key, id);
    return id;
  }

  function getBaseUrl() {
    const isApiServer = location.hostname === 'localhost' && location.port === '4321';
    return isApiServer ? '' : 'http://localhost:4321';
  }

  async function init() {
    if (state.initPromise) return state.initPromise;

    state.initPromise = (async () => {
      const res = await fetch(`${getBaseUrl()}/api/firebase-config`);
      const payload = await res.json();

      if (!payload.enabled || !payload.config) {
        state.disabled = true;
        return state;
      }

      const [{ initializeApp }, { getFirestore }, { getAuth, signInAnonymously }] = await Promise.all([
        import('https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js'),
        import('https://www.gstatic.com/firebasejs/10.12.5/firebase-firestore.js'),
        import('https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js')
      ]);

      const app = initializeApp(payload.config);
      const auth = getAuth(app);
      const credential = await signInAnonymously(auth);

      state.db = getFirestore(app);
      state.user = credential.user;

      if (payload.config.measurementId) {
        const { getAnalytics, isSupported } = await import('https://www.gstatic.com/firebasejs/10.12.5/firebase-analytics.js');
        if (await isSupported()) {
          state.analytics = getAnalytics(app);
        }
      }

      state.ready = true;
      return state;
    })().catch((err) => {
      state.disabled = true;
      console.warn('[Xyran Firebase] disabled:', err.message);
      return state;
    });

    return state.initPromise;
  }

  async function saveChat({ user, assistant, provider }) {
    const current = await init();
    if (!current.ready) return false;

    const [{ collection, doc, setDoc, addDoc, serverTimestamp }] = await Promise.all([
      import('https://www.gstatic.com/firebasejs/10.12.5/firebase-firestore.js')
    ]);

    const userRef = doc(current.db, 'users', current.user.uid);
    const chatRef = doc(userRef, 'chats', current.sessionId);

    await setDoc(userRef, {
      uid: current.user.uid,
      lastSeenAt: serverTimestamp()
    }, { merge: true });

    await setDoc(chatRef, {
      sessionId: current.sessionId,
      uid: current.user.uid,
      page: location.pathname,
      provider: provider || null,
      updatedAt: serverTimestamp()
    }, { merge: true });

    await addDoc(collection(chatRef, 'messages'), {
      user,
      assistant,
      provider: provider || null,
      createdAt: serverTimestamp()
    });

    return true;
  }

  window.XyranFirebase = {
    init,
    saveChat,
    get state() {
      return state;
    }
  };
})();
