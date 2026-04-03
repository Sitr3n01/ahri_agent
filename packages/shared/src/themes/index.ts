/**
 * Persona themes - migrado de web_ui.py THEMES_CONFIG.
 * Cada persona tem cores únicas para o sistema glassmorphism.
 */

export interface PersonaTheme {
  primary: string;
  secondary: string;
  shadow: string;
  glow: string;
  avatar: string;
  background: string;
  backgroundMobile: string;
}

export const personaThemes: Record<string, PersonaTheme> = {
  ahri: {
    primary: '#d8b4d8',
    secondary: '#e9cce9',
    shadow: 'rgba(192, 132, 192, 0.25)',
    glow: 'rgba(216, 180, 216, 0.6)',
    avatar: 'ahri_1.png',
    background: 'background_ahri.png',
    backgroundMobile: 'background_ahri_mobile.png',
  },
  kafka: {
    primary: '#800020',
    secondary: '#A52A2A',
    shadow: 'rgba(128, 0, 32, 0.4)',
    glow: 'rgba(165, 42, 42, 0.7)',
    avatar: 'kafka_1.png',
    background: 'background_kafka.png',
    backgroundMobile: 'background_kafka_mobile.png',
  },
  robin: {
    primary: '#9370DB',
    secondary: '#E6E6FA',
    shadow: 'rgba(147, 112, 219, 0.3)',
    glow: 'rgba(230, 230, 250, 0.5)',
    avatar: 'robin_1.png',
    background: 'background_robin.png',
    backgroundMobile: 'background_robin_mobile.png',
  },
  furina: {
    primary: '#4169E1',
    secondary: '#B0C4DE',
    shadow: 'rgba(65, 105, 225, 0.3)',
    glow: 'rgba(176, 196, 222, 0.5)',
    avatar: 'furina_1.png',
    background: 'background_furina.png',
    backgroundMobile: 'background_furina_mobile.png',
  },
  sparkle: {
    primary: '#FF69B4',
    secondary: '#FFB6C1',
    shadow: 'rgba(255, 105, 180, 0.3)',
    glow: 'rgba(255, 182, 193, 0.5)',
    avatar: 'sparkle_1.png',
    background: 'background_sparkle.png',
    backgroundMobile: 'background_sparkle_mobile.png',
  },
  frieren: {
    primary: '#C0C0C0',
    secondary: '#E8E8E8',
    shadow: 'rgba(192, 192, 192, 0.3)',
    glow: 'rgba(232, 232, 232, 0.5)',
    avatar: 'frieren_1.png',
    background: 'background_frieren.png',
    backgroundMobile: 'background_frieren_mobile.png',
  },
  herta: {
    primary: '#8B4513',
    secondary: '#DEB887',
    shadow: 'rgba(139, 69, 19, 0.3)',
    glow: 'rgba(222, 184, 135, 0.5)',
    avatar: 'herta_1.png',
    background: 'background_herta.png',
    backgroundMobile: 'background_herta_mobile.png',
  },
  shorekeeper: {
    primary: '#20B2AA',
    secondary: '#AFEEEE',
    shadow: 'rgba(32, 178, 170, 0.3)',
    glow: 'rgba(175, 238, 238, 0.5)',
    avatar: 'shorekeeper_1.png',
    background: 'background_shorekeeper.png',
    backgroundMobile: 'background_shorekeeper_mobile.png',
  },
  cantarella: {
    primary: '#483D8B',
    secondary: '#9370DB',
    shadow: 'rgba(72, 61, 139, 0.3)',
    glow: 'rgba(147, 112, 219, 0.5)',
    avatar: 'cantarella_1.png',
    background: 'background_cantarella.png',
    backgroundMobile: 'background_cantarella_mobile.png',
  },
  maomao: {
    primary: '#228B22',
    secondary: '#90EE90',
    shadow: 'rgba(34, 139, 34, 0.3)',
    glow: 'rgba(144, 238, 144, 0.5)',
    avatar: 'maomao_1.png',
    background: 'background_maomao.png',
    backgroundMobile: 'background_maomao_mobile.png',
  },
  'yae miko': {
    primary: '#FF69B4',
    secondary: '#FFE4E1',
    shadow: 'rgba(255, 105, 180, 0.3)',
    glow: 'rgba(255, 228, 225, 0.5)',
    avatar: 'yae_miko_1.png',
    background: 'background_yae_miko.png',
    backgroundMobile: 'background_yae_miko_mobile.png',
  },
  rakan: {
    primary: '#DAA520',
    secondary: '#FFD700',
    shadow: 'rgba(218, 165, 32, 0.3)',
    glow: 'rgba(255, 215, 0, 0.5)',
    avatar: 'rakan_1.png',
    background: 'background_rakan.png',
    backgroundMobile: 'background_rakan_mobile.png',
  },
  'march 7th': {
    primary: '#FF6B81',
    secondary: '#FFDEE2',
    shadow: 'rgba(255, 107, 129, 0.3)',
    glow: 'rgba(255, 222, 226, 0.5)',
    avatar: 'march_7th_1.png',
    background: 'background_march_7th.png',
    backgroundMobile: 'background_march_7th_mobile.png',
  },
  cartethyia: {
    primary: '#4B0082',
    secondary: '#9932CC',
    shadow: 'rgba(75, 0, 130, 0.3)',
    glow: 'rgba(153, 50, 204, 0.5)',
    avatar: 'cartethyia_1.png',
    background: 'background_cartethyia.png',
    backgroundMobile: 'background_cartethyia_mobile.png',
  },
  cyrene: {
    primary: '#00CED1',
    secondary: '#E0FFFF',
    shadow: 'rgba(0, 206, 209, 0.3)',
    glow: 'rgba(224, 255, 255, 0.5)',
    avatar: 'cyrene_1.png',
    background: 'background_cyrene.png',
    backgroundMobile: 'background_cyrene_mobile.png',
  },
  'carlotta montelli': {
    primary: '#C71585',
    secondary: '#FF82AB',
    shadow: 'rgba(199, 21, 133, 0.3)',
    glow: 'rgba(255, 130, 171, 0.5)',
    avatar: 'carlotta_1.png',
    background: 'background_carlotta.png',
    backgroundMobile: 'background_carlotta_mobile.png',
  },
} as const;

export const DEFAULT_PERSONA = 'ahri';

export function getPersonaTheme(name: string): PersonaTheme {
  const key = name.toLowerCase().replace(/_/g, ' ');
  return personaThemes[key] ?? personaThemes[DEFAULT_PERSONA];
}

/**
 * Mescla o tema estático (hardcoded) com possíveis overrides dinâmicos vindos do banco de dados.
 */
export function mergePersonaTheme(staticTheme: PersonaTheme, overrides?: Partial<PersonaTheme>): PersonaTheme {
  if (!overrides) return staticTheme;
  return {
    ...staticTheme,
    primary: overrides.primary || staticTheme.primary,
    secondary: overrides.secondary || staticTheme.secondary,
    shadow: overrides.shadow || staticTheme.shadow,
    glow: overrides.glow || staticTheme.glow,
    avatar: overrides.avatar || staticTheme.avatar,
    background: overrides.background || staticTheme.background,
    backgroundMobile: overrides.backgroundMobile || staticTheme.backgroundMobile,
  };
}
