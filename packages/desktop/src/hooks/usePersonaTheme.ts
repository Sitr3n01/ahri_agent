import { useMemo } from 'react';
import { usePersonaStore } from '@/stores/persona-store';
import { type PersonaTheme } from '@ahri/shared';

/**
 * Hook para obter o tema da persona ativa (ou de uma persona específica),
 * mesclando as configurações estáticas com os overrides dinâmicos do backend.
 */
export function usePersonaTheme(personaName?: string): PersonaTheme {
  const activePersona = usePersonaStore((s) => s.activePersona);
  const personas = usePersonaStore((s) => s.personas);
  const getMergedTheme = usePersonaStore((s) => s.getMergedTheme);
  
  return useMemo(() => {
    return getMergedTheme(personaName || activePersona);
  }, [personaName, activePersona, personas, getMergedTheme]);
}
