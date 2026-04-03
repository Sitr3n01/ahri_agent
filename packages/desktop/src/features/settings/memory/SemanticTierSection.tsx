/**
 * SemanticTierSection — displays and manages one Layer 2 memory tier.
 *
 * Fetches all tiers on mount (shared call), filters to its own tier,
 * renders MemoryFactCards, and optionally allows deletion.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { Trash2, RefreshCw } from 'lucide-react';
import { api } from '@/api/client';
import type { SemanticMemoryItem, MemoryTier } from '@ahri/shared/types/memory';
import { MemoryFactCard } from './MemoryFactCard';

interface SemanticTierSectionProps {
  tier: MemoryTier;
  label: string;
  /** Whether individual fact deletion is allowed (volatile tiers only) */
  allowDelete?: boolean;
  /** Externally fetched tiers data — avoids re-fetching if parent already loaded */
  tiersData?: Record<string, SemanticMemoryItem[]>;
  /** Callback to refresh parent data */
  onRefresh?: () => void;
}

export function SemanticTierSection({
  tier,
  label,
  allowDelete = false,
  tiersData,
  onRefresh,
}: SemanticTierSectionProps) {
  const [items, setItems] = useState<SemanticMemoryItem[]>([]);
  const [loading, setLoading] = useState(!tiersData);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    if (tiersData) {
      setItems(tiersData[tier] || []);
      setLoading(false);
    }
  }, [tiersData, tier]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getSemanticTier(tier);
      setItems(data);
    } catch (err) {
      console.error(`Failed to load tier ${tier}:`, err);
    } finally {
      setLoading(false);
    }
  }, [tier]);

  // Only self-fetch if no external tiersData provided
  useEffect(() => {
    if (!tiersData) load();
  }, [tiersData, load]);

  const handleDelete = async (id: number) => {
    try {
      await api.deleteSemanticFact(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
      onRefresh?.();
    } catch (err) {
      console.error('Failed to delete fact:', err);
    }
  };

  const handleClearAll = async () => {
    if (!confirm(`Limpar todos os itens de "${label}"?`)) return;
    setClearing(true);
    try {
      await api.deleteSemanticTier(tier);
      setItems([]);
      onRefresh?.();
    } catch (err) {
      console.error('Failed to clear tier:', err);
    } finally {
      setClearing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-4">
        <RefreshCw size={14} className="animate-spin" style={{ color: 'var(--text-tertiary)' }} />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <p className="text-xs py-2 italic" style={{ color: 'var(--text-tertiary)' }}>
        Nenhum fato neste tier ainda.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {/* Items */}
      {items.map((item) => (
        <MemoryFactCard
          key={item.id}
          item={item}
          onDelete={allowDelete ? handleDelete : undefined}
        />
      ))}

      {/* Clear all button (for volatile tiers) */}
      {allowDelete && items.length > 0 && (
        <button
          onClick={handleClearAll}
          disabled={clearing}
          className="flex items-center gap-1.5 text-xs mt-1 opacity-50 hover:opacity-100 transition-opacity"
          style={{ color: 'var(--text-tertiary)' }}
        >
          {clearing ? <RefreshCw size={11} className="animate-spin" /> : <Trash2 size={11} />}
          Limpar tier
        </button>
      )}
    </div>
  );
}
