import { useState, useRef, useEffect } from 'react';
import { usePersonaStore } from '@/stores/persona-store';
import { getPersonaTheme } from '@ahri/shared';

/**
 * Per-persona image position config.
 * Adjust these to center on each character's eyes/face.
 * Format: CSS object-position value (e.g., "50% 30%" means center horizontally, 30% from top)
 */
const PERSONA_IMAGE_POSITIONS: Record<string, string> = {
    ahri: '50% 20%',
    kafka: '50% 20%',
    robin: '50% 20%',
    furina: '50% 20%',
    sparkle: '50% 20%',
    frieren: '50% 20%',
    herta: '50% 20%',
    shorekeeper: '50% 20%',
    cantarella: '50% 20%',
    maomao: '50% 20%',
    'yae miko': '50% 20%',
    rakan: '50% 20%',
    'march 7th': '50% 20%',
    cartethyia: '50% 20%',
    cyrene: '50% 20%',
    'carlotta montelli': '50% 20%',
};

function getImagePosition(name: string): string {
    return PERSONA_IMAGE_POSITIONS[name.toLowerCase().replace(/_/g, ' ')] || '50% 20%';
}

export function PersonaDrawer() {
    const activePersona = usePersonaStore((s) => s.activePersona);
    const personas = usePersonaStore((s) => s.personas);
    const activatePersona = usePersonaStore((s) => s.activatePersona);
    const isLoading = usePersonaStore((s) => s.isLoading);
    const error = usePersonaStore((s) => s.error);
    const fetchPersonas = usePersonaStore((s) => s.fetchPersonas);

    const [isOpen, setIsOpen] = useState(false);
    const [hoveredPersona, setHoveredPersona] = useState<string | null>(null);
    const drawerRef = useRef<HTMLDivElement>(null);
    const contentRef = useRef<HTMLDivElement>(null);

    const activeTheme = getPersonaTheme(activePersona);
    const activePersonaData = personas.find((p) => p.name === activePersona);

    // Close drawer when clicking outside
    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (drawerRef.current && !drawerRef.current.contains(e.target as Node)) {
                setIsOpen(false);
            }
        };
        if (isOpen) {
            document.addEventListener('mousedown', handleClickOutside);
        }
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, [isOpen]);

    const handleSelectPersona = (name: string) => {
        activatePersona(name);
        setIsOpen(false);
    };

    if (isLoading) {
        return (
            <div className="persona-drawer-skeleton">
                <div className="persona-drawer-skeleton-bar" />
            </div>
        );
    }

    if (error) {
        return (
            <div className="text-xs py-3 text-center space-y-2">
                <p style={{ color: 'rgba(239, 68, 68, 0.7)' }}>Erro ao carregar personas</p>
                <button
                    onClick={() => fetchPersonas()}
                    className="px-3 py-1 rounded-lg text-[10px] font-medium transition-all"
                    style={{
                        background: 'rgba(139, 92, 246, 0.15)',
                        color: '#a78bfa',
                        border: '1px solid rgba(139, 92, 246, 0.3)',
                    }}
                >
                    Tentar novamente
                </button>
            </div>
        );
    }

    if (personas.length === 0) {
        return (
            <div className="text-xs py-3 text-center" style={{ color: 'var(--text-tertiary)' }}>
                Nenhuma persona encontrada
            </div>
        );
    }

    return (
        <div className="persona-drawer-wrapper" ref={drawerRef}>
            {/* Toggle Button — shows active persona preview */}
            <button
                className="persona-drawer-toggle"
                onClick={() => setIsOpen(!isOpen)}
                style={{
                    '--drawer-color': activeTheme.primary,
                    '--drawer-shadow': activeTheme.shadow,
                    '--drawer-glow': activeTheme.glow,
                } as React.CSSProperties}
            >
                <div className="persona-drawer-toggle-preview">
                    <img
                        src={`/${activeTheme.background}`}
                        alt={activePersonaData?.display_name || activePersona}
                        className="persona-drawer-toggle-img"
                        style={{ objectPosition: getImagePosition(activePersona) }}
                        draggable={false}
                    />
                    <div className="persona-drawer-toggle-overlay" />
                    <div className="persona-drawer-toggle-info">
                        <svg
                            width="14"
                            height="14"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2.5"
                            className={`persona-drawer-chevron ${isOpen ? 'open' : ''}`}
                            style={{ margin: 'auto' }}
                        >
                            <polyline points="6 9 12 15 18 9" />
                        </svg>
                    </div>
                </div>
            </button>

            {/* Drawer Content */}
            <div
                className={`persona-drawer-content ${isOpen ? 'open' : ''}`}
                ref={contentRef}
                style={{
                    maxHeight: isOpen ? '420px' : '0px',
                }}
            >
                <div className="persona-drawer-list">
                    {personas.filter((p) => p.name !== activePersona).map((p) => {
                        const pTheme = getPersonaTheme(p.name);
                        const isActive = p.name === activePersona;
                        const isHovered = hoveredPersona === p.name;

                        return (
                            <button
                                key={p.name}
                                className={`persona-drawer-item ${isActive ? 'active' : ''}`}
                                onClick={() => handleSelectPersona(p.name)}
                                onMouseEnter={() => setHoveredPersona(p.name)}
                                onMouseLeave={() => setHoveredPersona(null)}
                                style={{
                                    '--item-color': pTheme.primary,
                                    '--item-shadow': pTheme.shadow,
                                    '--item-glow': pTheme.glow,
                                } as React.CSSProperties}
                            >
                                {/* Ultra-wide image */}
                                <div className="persona-drawer-item-image-container">
                                    <img
                                        src={`/${pTheme.background}`}
                                        alt={p.display_name}
                                        className="persona-drawer-item-image"
                                        style={{ objectPosition: getImagePosition(p.name) }}
                                        draggable={false}
                                        onError={(e) => {
                                            const target = e.target as HTMLImageElement;
                                            target.style.display = 'none';
                                        }}
                                    />
                                    {/* Gradient overlay */}
                                    <div className="persona-drawer-item-gradient" />

                                    {/* Active indicator glow bar */}
                                    {isActive && <div className="persona-drawer-item-active-bar" />}

                                    {/* Name overlay */}
                                    <div className="persona-drawer-item-info">
                                        <span className="persona-drawer-item-name">{p.display_name}</span>
                                        {isActive && (
                                            <div className="persona-drawer-item-badge">
                                                <div className="persona-drawer-item-badge-dot" />
                                                <span>Ativa</span>
                                            </div>
                                        )}
                                    </div>

                                    {/* Hover shimmer effect */}
                                    {(isHovered && !isActive) && (
                                        <div className="persona-drawer-item-shimmer" />
                                    )}
                                </div>
                            </button>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
