import React, { useState } from 'react';
import { X, Plus } from 'lucide-react';

interface TagInputProps {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
}

export function TagInput({ tags, onChange, placeholder }: TagInputProps) {
  const [inputValue, setInputValue] = useState('');

  const addTag = () => {
    const trimmed = inputValue.trim();
    if (trimmed && !tags.includes(trimmed)) {
      onChange([...tags, trimmed]);
      setInputValue('');
    }
  };

  const removeTag = (tagToRemove: string) => {
    onChange(tags.filter(t => t !== tagToRemove));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addTag();
    }
  };

  return (
    <div className="flex flex-wrap gap-2 p-3 rounded-lg border border-[var(--glass-border)] bg-[var(--surface-solid)] focus-within:border-[var(--persona-primary)]/50 transition-all min-h-[42px]">
      {tags.map((tag, idx) => (
        <span 
          key={`${tag}-${idx}`}
          className="flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium bg-purple-500/10 text-purple-300 border border-purple-500/20 group"
        >
          {tag}
          <button
            onClick={() => removeTag(tag)}
            className="hover:text-red-400 transition-colors"
          >
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        type="text"
        value={inputValue}
        onChange={(e) => setInputValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={addTag}
        placeholder={tags.length === 0 ? placeholder : ''}
        className="flex-1 bg-transparent border-none outline-none text-xs text-[var(--text-primary)] min-w-[80px]"
      />
    </div>
  );
}
