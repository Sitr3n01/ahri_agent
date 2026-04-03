const fs = require('fs');
const file = 'packages/desktop/src/features/settings/SettingsView.tsx';
const content = fs.readFileSync(file, 'utf-8');
const lines = content.split('\n');

const newContent = `  return (
    <div className="flex h-full w-full bg-[var(--bg-primary)] text-[var(--text-primary)] relative items-start" style={{ background: 'var(--bg-primary, #ffffff)' }}>
      {/* Sidebar */}
      <aside className="w-64 h-full flex-shrink-0 flex flex-col border-r relative z-10 shadow-sm" style={{ borderColor: 'var(--glass-border)', background: 'var(--bg-secondary, rgba(0,0,0,0.02))' }}>
        {/* Sidebar Header */}
        <div className="p-6 pb-2">
          <h1
            className="text-2xl font-bold tracking-tight mb-1"
            style={{
              background: 'linear-gradient(135deg, var(--persona-primary) 0%, var(--persona-secondary) 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            {t('settings.title')}
          </h1>
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {t('settings.subtitle')}
          </p>
        </div>

        {/* Sidebar Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={\`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all \${activeTab === tab.id ? 'active' : ''}\`}
              style={activeTab === tab.id 
                ? { background: 'var(--persona-primary)', color: '#fff', boxShadow: '0 4px 12px color-mix(in srgb, var(--persona-shadow) 30%, transparent)' } 
                : { color: 'var(--text-secondary)' }
              }
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>

        {/* Utilities Footer */}
        <div className="p-4 border-t flex flex-col gap-4" style={{ borderColor: 'var(--glass-border)', background: 'var(--bg-primary)' }}>
          {savedFeedback && (
            <div className="flex items-center gap-2 text-xs text-emerald-500 font-medium px-2 animate-fade-in">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M20 6L9 17l-5-5" /></svg>
              {savedFeedback}
            </div>
          )}
          
          <div className="flex items-center justify-between">
            <div className="flex items-center p-0.5 rounded-lg border" style={{ borderColor: 'var(--glass-border)', background: 'rgba(128, 128, 128, 0.05)' }}>
              <button 
                onClick={() => setLocale('pt')} 
                className="px-2 py-1.5 rounded-md text-[10px] font-bold uppercase transition-all" 
                style={locale === 'pt' ? { background: 'var(--persona-primary)', color: '#fff' } : { color: 'var(--text-tertiary)' }}
              >
                PT
              </button>
              <button 
                onClick={() => setLocale('en')} 
                className="px-2 py-1.5 rounded-md text-[10px] font-bold uppercase transition-all" 
                style={locale === 'en' ? { background: 'var(--persona-primary)', color: '#fff' } : { color: 'var(--text-tertiary)' }}
              >
                EN
              </button>
            </div>

            <div className="flex items-center gap-1">
              <button onClick={toggleTheme} className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition-colors" style={{ color: 'var(--text-secondary)' }} title={appTheme === 'dark' ? t('common.theme_light') : t('common.theme_dark')}>
                {appTheme === 'dark' ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" /></svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
                )}
              </button>
              
              <button onClick={logout} className="p-2 rounded-lg text-red-500 hover:bg-red-500/10 transition-colors" title={t('nav.logout')}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></svg>
              </button>
              
              {onClose && (
                <button onClick={onClose} className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition-colors" style={{ color: 'var(--text-secondary)' }} title={t('common.close')}>
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                </button>
              )}
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col h-full min-w-0 relative z-10 overflow-hidden">
        <div key={activeTab} className="flex-1 flex flex-col h-full w-full animate-fade-in p-6 lg:p-10" style={{ animationDuration: '0.35s' }}>
          <div className="max-w-4xl w-full h-full flex flex-col mx-auto">
            {activeTab === 'api-keys' && <ApiKeysTab config={apiKeys} onChange={setApiKeys} onSave={handleSaveApiKeys} />}
            {activeTab === 'chat' && <ChatTab config={chatConfig} onChange={setChatConfig} onSave={handleSaveChatConfig} />}
            {activeTab === 'agent' && <AgentTab config={agentConfig} onChange={setAgentConfig} onSave={handleSaveAgentConfig} />}
            {activeTab === 'profile' && <ProfileTab config={userProfile} onChange={setUserProfile} onSave={handleSaveProfile} />}
            {activeTab === 'personas' && (
              <PersonasTab
                personas={personas}
                selectedPersona={selectedPersona}
                activePersona={activePersona}
                editedData={editedData}
                hasChanges={hasChanges}
                currentTheme={currentTheme}
                onSelectPersona={(name) => {
                  if (hasChanges && !confirm(t('persona.unsaved_confirm'))) return;
                  setSelectedPersona(name);
                }}
                onFieldChange={handlePersonaFieldChange}
                onSave={handlePersonaSave}
                onCancel={handlePersonaCancel}
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );`;

let startIdx = lines.findIndex(l => l.includes('  return (') && lines.indexOf(l) > 400);
let endIdx = lines.findIndex((l, i) => l.includes('  );') && i > startIdx && lines[i+2].includes('// ── API Keys Tab'));

if (startIdx !== -1 && endIdx !== -1) {
  lines.splice(startIdx, endIdx - startIdx + 1, newContent);
  fs.writeFileSync(file, lines.join('\\n'));
  console.log('Success');
} else {
  console.log('Indexes not found', startIdx, endIdx);
}
