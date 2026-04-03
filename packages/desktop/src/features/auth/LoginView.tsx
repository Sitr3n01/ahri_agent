import { useState, useEffect, useMemo } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { usePersonaStore } from '@/stores/persona-store';
import { api } from '@/api/client';

// Firefly positions — fixed so they don't re-generate on re-render
const FIREFLIES = [
  { x: 12,  y: 20,  dur: 9,  delay: 0   },
  { x: 28,  y: 65,  dur: 11, delay: 1.5 },
  { x: 55,  y: 15,  dur: 8,  delay: 0.8 },
  { x: 72,  y: 78,  dur: 13, delay: 2.2 },
  { x: 85,  y: 40,  dur: 7,  delay: 0.4 },
  { x: 42,  y: 88,  dur: 10, delay: 3.1 },
  { x: 93,  y: 12,  dur: 12, delay: 1.8 },
];

export function LoginView() {
  const [password, setPassword] = useState('');
  const login = useAuthStore((s) => s.login);
  const isLoading = useAuthStore((s) => s.isLoading);
  const error = useAuthStore((s) => s.error);
  const personas = usePersonaStore((s) => s.personas);

  const [showReset, setShowReset] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [resetStatus, setResetStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [resetError, setResetError] = useState('');

  const [backendStatus, setBackendStatus] = useState<'connecting' | 'connected' | 'failed'>('connecting');

  useEffect(() => {
    let cancelled = false;
    let intervalId: any;

    const checkBackend = async () => {
      try {
        await api.health();
        if (!cancelled) setBackendStatus('connected');
      } catch {
        if (!cancelled) setBackendStatus('failed');
      }
    };

    checkBackend();
    
    // Poll every 3 seconds to auto-reconnect if it fails
    intervalId = setInterval(checkBackend, 3000);

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) return;
    await login(password);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      setPassword('');
    }
  };

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 4) {
      setResetError('Senha deve ter pelo menos 4 caracteres');
      return;
    }
    if (newPassword !== confirmPassword) {
      setResetError('As senhas não coincidem');
      return;
    }
    setResetStatus('loading');
    setResetError('');
    try {
      await api.forceResetPassword(newPassword);
      setResetStatus('success');
      setNewPassword('');
      setConfirmPassword('');
      // After 2s, go back to login form
      setTimeout(() => {
        setShowReset(false);
        setResetStatus('idle');
      }, 2000);
    } catch (err) {
      setResetStatus('error');
      setResetError(err instanceof Error ? err.message : 'Erro ao resetar senha');
    }
  };

  const statusItems = useMemo(() => [
    {
      label: 'Backend',
      status: backendStatus,
      text: backendStatus === 'connecting' ? 'Conectando...' : backendStatus === 'connected' ? 'Online' : 'Offline',
      color: backendStatus === 'connecting' ? '#f59e0b' : backendStatus === 'connected' ? '#22c55e' : '#ef4444',
    },
    { label: 'LLM', status: 'connected', text: '4 Motores', color: '#22c55e' },
    { label: 'Personas', status: 'connected', text: `${personas.length || 17} Carregadas`, color: '#3b82f6' },
    { label: 'Agente', status: 'connected', text: 'Ativo', color: '#8b5cf6' },
  ], [backendStatus, personas.length]);

  return (
    <div
      className="h-screen w-screen flex items-center justify-center overflow-hidden relative"
      style={{ background: 'rgba(6, 4, 12, 1)' }}
    >
      {/* Persona background */}
      <div
        className="absolute inset-0 z-0"
        style={{
          backgroundImage: "url('/background_ahri.png')",
          backgroundSize: 'cover',
          backgroundPosition: 'center top',
          opacity: 0.28,
        }}
      />
      {/* Vignette */}
      <div
        className="absolute inset-0 z-0"
        style={{
          background: 'radial-gradient(ellipse at 65% 40%, rgba(0,0,0,0.05) 0%, rgba(0,0,0,0.70) 100%)',
        }}
      />

      {/* Fireflies */}
      {FIREFLIES.map((ff, i) => (
        <div
          key={i}
          className="vn-firefly z-10"
          style={{
            left: `${ff.x}%`,
            top: `${ff.y}%`,
            '--ff-dur': `${ff.dur}s`,
            '--ff-delay': `${ff.delay}s`,
          } as React.CSSProperties}
        />
      ))}

      {/* Login card */}
      <div className="relative z-20 w-full max-w-sm px-6">
        {/* Logo / Title */}
        <div className="text-center mb-8">
          {/* Persona avatar */}
          <div
            className="w-20 h-20 mx-auto mb-5 rounded-full overflow-hidden"
            style={{
              border: '2px solid rgba(216, 180, 216, 0.6)',
              boxShadow: '0 0 28px rgba(192,132,192,0.5), 0 0 60px rgba(216,180,216,0.25)',
            }}
          >
            <img
              src="/ahri_1.png"
              alt="Ahri"
              className="w-full h-full object-cover"
              onError={(e) => {
                const t = e.target as HTMLImageElement;
                t.style.display = 'none';
                t.parentElement!.style.background = 'rgba(216,180,216,0.3)';
              }}
            />
          </div>

          <h1
            className="text-3xl font-bold tracking-tight mb-1"
            style={{
              background: 'linear-gradient(135deg, #d8b4d8 0%, #e9cce9 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              letterSpacing: '-0.02em',
            }}
          >
            Ahri
          </h1>
          <p
            className="text-xs tracking-[0.25em] uppercase"
            style={{ color: 'rgba(216,180,216,0.45)', fontFamily: 'var(--font-mono)' }}
          >
            v3 · Companion System
          </p>
        </div>

        {/* Form card */}
        <div
          className="vn-card p-6 mb-4"
          style={{
            '--persona-primary': '#d8b4d8',
            '--persona-secondary': '#e9cce9',
            '--persona-shadow': 'rgba(192,132,192,0.25)',
            '--persona-glow': 'rgba(216,180,216,0.6)',
          } as React.CSSProperties}
        >
          {!showReset ? (
            /* ── Login Form ── */
            <form onSubmit={handleSubmit}>
              <div className="mb-4">
                <label
                  htmlFor="password-input"
                  className="block text-xs mb-2 tracking-widest uppercase"
                  style={{ color: 'rgba(216,180,216,0.55)', fontFamily: 'var(--font-mono)' }}
                >
                  Senha de acesso
                </label>
                <input
                  id="password-input"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="••••••••"
                  autoFocus
                  className="agent-input w-full text-base"
                  style={{
                    '--persona-primary': '#d8b4d8',
                    '--persona-shadow': 'rgba(192,132,192,0.25)',
                    borderRadius: '10px',
                    padding: '10px 14px',
                  } as React.CSSProperties}
                />
              </div>

              {error && (
                <div
                  className="mb-4 p-3 rounded-lg text-xs"
                  style={{
                    background: 'rgba(239,68,68,0.08)',
                    border: '1px solid rgba(239,68,68,0.25)',
                    color: '#ef4444',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {error}
                </div>
              )}

              <button
                type="submit"
                disabled={isLoading || !password.trim() || backendStatus !== 'connected'}
                className="agent-button-primary w-full"
                style={{
                  '--persona-primary': '#d8b4d8',
                  '--persona-secondary': '#e9cce9',
                  '--persona-shadow': 'rgba(192,132,192,0.25)',
                  borderRadius: '10px',
                  padding: '11px',
                  fontSize: '14px',
                  letterSpacing: '0.08em',
                } as React.CSSProperties}
              >
                {isLoading ? 'Entrando...' : 'Entrar'}
              </button>

              <button
                type="button"
                onClick={() => { setShowReset(true); setResetError(''); setResetStatus('idle'); }}
                className="w-full mt-3 text-xs transition-colors duration-150"
                style={{ color: 'rgba(216,180,216,0.4)', fontFamily: 'var(--font-mono)' }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'rgba(216,180,216,0.7)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'rgba(216,180,216,0.4)')}
              >
                Esqueceu a senha?
              </button>
            </form>
          ) : (
            /* ── Password Reset Form ── */
            <form onSubmit={handleReset}>
              <div className="mb-3">
                <label
                  className="block text-xs mb-2 tracking-widest uppercase"
                  style={{ color: 'rgba(216,180,216,0.55)', fontFamily: 'var(--font-mono)' }}
                >
                  Nova senha
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Mínimo 4 caracteres"
                  autoFocus
                  className="agent-input w-full text-base"
                  style={{
                    '--persona-primary': '#d8b4d8',
                    '--persona-shadow': 'rgba(192,132,192,0.25)',
                    borderRadius: '10px',
                    padding: '10px 14px',
                  } as React.CSSProperties}
                />
              </div>

              <div className="mb-4">
                <label
                  className="block text-xs mb-2 tracking-widest uppercase"
                  style={{ color: 'rgba(216,180,216,0.55)', fontFamily: 'var(--font-mono)' }}
                >
                  Confirmar senha
                </label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repita a nova senha"
                  className="agent-input w-full text-base"
                  style={{
                    '--persona-primary': '#d8b4d8',
                    '--persona-shadow': 'rgba(192,132,192,0.25)',
                    borderRadius: '10px',
                    padding: '10px 14px',
                  } as React.CSSProperties}
                />
              </div>

              {resetStatus === 'success' && (
                <div
                  className="mb-4 p-3 rounded-lg text-xs"
                  style={{
                    background: 'rgba(34,197,94,0.08)',
                    border: '1px solid rgba(34,197,94,0.25)',
                    color: '#22c55e',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  Senha atualizada com sucesso! Redirecionando...
                </div>
              )}

              {resetError && (
                <div
                  className="mb-4 p-3 rounded-lg text-xs"
                  style={{
                    background: 'rgba(239,68,68,0.08)',
                    border: '1px solid rgba(239,68,68,0.25)',
                    color: '#ef4444',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {resetError}
                </div>
              )}

              <button
                type="submit"
                disabled={resetStatus === 'loading' || !newPassword || !confirmPassword}
                className="agent-button-primary w-full"
                style={{
                  '--persona-primary': '#d8b4d8',
                  '--persona-secondary': '#e9cce9',
                  '--persona-shadow': 'rgba(192,132,192,0.25)',
                  borderRadius: '10px',
                  padding: '11px',
                  fontSize: '14px',
                  letterSpacing: '0.08em',
                } as React.CSSProperties}
              >
                {resetStatus === 'loading' ? 'Alterando...' : 'Redefinir Senha'}
              </button>

              <button
                type="button"
                onClick={() => { setShowReset(false); setResetError(''); }}
                className="w-full mt-3 text-xs transition-colors duration-150"
                style={{ color: 'rgba(216,180,216,0.4)', fontFamily: 'var(--font-mono)' }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'rgba(216,180,216,0.7)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'rgba(216,180,216,0.4)')}
              >
                Voltar ao login
              </button>
            </form>
          )}
        </div>

        {/* Status indicators */}
        <div
          className="rounded-xl px-4 py-3 grid grid-cols-2 gap-2"
          style={{
            background: 'rgba(10, 8, 20, 0.70)',
            border: '1px solid rgba(216,180,216,0.12)',
            backdropFilter: 'blur(30px)',
          }}
        >
          {statusItems.map((item) => (
            <div key={item.label} className="flex items-center gap-2">
              <div
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{
                  background: item.color,
                  boxShadow: `0 0 6px ${item.color}`,
                  animation: item.status === 'connecting' ? 'pulse 1s ease-in-out infinite' : undefined,
                }}
              />
              <div>
                <div
                  className="text-[9px] uppercase tracking-wider leading-none"
                  style={{ color: 'rgba(255,255,255,0.3)', fontFamily: 'var(--font-mono)' }}
                >
                  {item.label}
                </div>
                <div
                  className="text-[11px] font-medium leading-tight mt-0.5"
                  style={{ color: item.color }}
                >
                  {item.text}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
