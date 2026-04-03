import React, { useState, useEffect, useRef, useCallback } from 'react';

interface ColorPickerProps {
  color: string;
  onChange: (hex: string) => void;
  onClose: () => void;
}

/**
 * Helper to convert HEX to HSV (Hue, Saturation, Value)
 */
function hexToHsv(hex: string) {
  let r = 0, g = 0, b = 0;
  if (hex.length === 4) {
    r = parseInt(hex[1] + hex[1], 16);
    g = parseInt(hex[2] + hex[2], 16);
    b = parseInt(hex[3] + hex[3], 16);
  } else if (hex.length === 7) {
    r = parseInt(hex.substring(1, 3), 16);
    g = parseInt(hex.substring(3, 5), 16);
    b = parseInt(hex.substring(5, 7), 16);
  }
  
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0, v = max;
  const d = max - min;
  s = max === 0 ? 0 : d / max;

  if (max !== min) {
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      case b: h = (r - g) / d + 4; break;
    }
    h /= 6;
  }
  return { h: h * 360, s: s * 100, v: v * 100 };
}

/**
 * Helper to convert HSV to HEX
 */
function hsvToHex(h: number, s: number, v: number) {
  s /= 100; v /= 100;
  const i = Math.floor(h / 60);
  const f = h / 60 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);
  
  let r = 0, g = 0, b = 0;
  switch (i % 6) {
    case 0: r = v; g = t; b = p; break;
    case 1: r = q; g = v; b = p; break;
    case 2: r = p; g = v; b = t; break;
    case 3: r = p; g = q; b = v; break;
    case 4: r = t; g = p; b = v; break;
    case 5: r = v; g = p; b = q; break;
  }
  
  const toHex = (n: number) => {
    const hex = Math.round(n * 255).toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  };
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`.toUpperCase();
}

export const ColorPicker: React.FC<ColorPickerProps> = ({ color, onChange, onClose }) => {
  const [hsv, setHsv] = useState(() => hexToHsv(color));
  const [isMouseDown, setIsMouseDown] = useState(false);
  const [position, setPosition] = useState<'top' | 'bottom'>('bottom');
  const pickerRef = useRef<HTMLDivElement>(null);
  const satRef = useRef<HTMLDivElement>(null);

  // Sync internal state if external color changes
  useEffect(() => {
    const currentHex = hsvToHex(hsv.h, hsv.s, hsv.v);
    if (currentHex !== color.toUpperCase()) {
      setHsv(hexToHsv(color));
    }
  }, [color]);

  // Determine positioning (top or bottom)
  useEffect(() => {
    if (pickerRef.current) {
      const rect = pickerRef.current.getBoundingClientRect();
      const pickerHeight = 260; // Approximate height of the compact picker
      const spaceBelow = window.innerHeight - rect.top; // Measured from the trigger point
      
      if (spaceBelow < pickerHeight + 100) {
        setPosition('top');
      } else {
        setPosition('bottom');
      }
    }
  }, []);

  const handleSatMouseDown = (e: React.MouseEvent | React.TouchEvent) => {
    setIsMouseDown(true);
    updateSaturation(e);
  };

  const updateSaturation = useCallback((e: React.MouseEvent | React.TouchEvent | MouseEvent | TouchEvent) => {
    if (!satRef.current) return;
    const rect = satRef.current.getBoundingClientRect();
    const x = 'touches' in e ? e.touches[0].clientX : (e as MouseEvent).clientX;
    const y = 'touches' in e ? e.touches[0].clientY : (e as MouseEvent).clientY;
    
    let s = ((x - rect.left) / rect.width) * 100;
    let v = 100 - ((y - rect.top) / rect.height) * 100;
    
    s = Math.max(0, Math.min(100, s));
    v = Math.max(0, Math.min(100, v));
    
    setHsv(prev => {
      const next = { ...prev, s, v };
      onChange(hsvToHex(next.h, next.s, next.v));
      return next;
    });
  }, [onChange]);

  const updateHue = (e: React.ChangeEvent<HTMLInputElement>) => {
    const h = parseInt(e.target.value);
    setHsv(prev => {
      const next = { ...prev, h };
      onChange(hsvToHex(next.h, next.s, next.v));
      return next;
    });
  };

  useEffect(() => {
    const handleGlobalMouseMove = (e: MouseEvent) => {
      if (isMouseDown) updateSaturation(e);
    };
    const handleGlobalMouseUp = () => {
      setIsMouseDown(false);
    };

    if (isMouseDown) {
      window.addEventListener('mousemove', handleGlobalMouseMove);
      window.addEventListener('mouseup', handleGlobalMouseUp);
    }
    return () => {
      window.removeEventListener('mousemove', handleGlobalMouseMove);
      window.removeEventListener('mouseup', handleGlobalMouseUp);
    };
  }, [isMouseDown, updateSaturation]);

  // Handle click outside to close
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  return (
    <div 
      ref={pickerRef}
      className={`absolute z-[100] p-3 rounded-xl border bg-[var(--surface-solid)] shadow-xl transition-all duration-200 ease-out origin-top ${
        position === 'top' ? 'bottom-full mb-2' : 'top-full mt-2'
      }`}
      style={{ 
        width: '190px', 
        left: '0',
        borderColor: 'var(--glass-border)',
        animation: 'pickerFadeIn 0.2s ease-out forwards',
        opacity: 0,
        transform: 'translateY(4px) scale(0.98)',
        backdropFilter: 'none'
      }}
    >
      <div 
        ref={satRef}
        onMouseDown={handleSatMouseDown}
        className="relative w-full h-20 mb-3 cursor-crosshair overflow-hidden border border-[var(--glass-border)] rounded-lg"
        style={{ 
          background: `
            linear-gradient(to top, #000, transparent),
            linear-gradient(to right, #fff, transparent),
            hsl(${hsv.h}, 100%, 50%)
          `
        }}
      >
        {/* Selector Dot */}
        <div 
          className="absolute w-2.5 h-2.5 border border-white rounded-full pointer-events-none -translate-x-1/2 translate-y-1/2 shadow-sm"
          style={{ 
            left: `${hsv.s}%`, 
            bottom: `${hsv.v}%`,
          }}
        />
      </div>

      {/* Hue Slider */}
      <div className="mb-3">
        <input 
          type="range"
          min="0"
          max="360"
          value={hsv.h}
          onChange={updateHue}
          className="w-full h-1.5 rounded-full appearance-none cursor-pointer border border-[var(--glass-border)]"
          style={{ 
            background: 'linear-gradient(to right, #f00 0%, #ff0 17%, #0f0 33%, #0ff 50%, #00f 67%, #f0f 83%, #f00 100%)'
          }}
        />
      </div>

      {/* Hex Manual Input */}
      <div className="flex items-center">
        <input 
          type="text"
          value={color}
          onChange={(e) => {
            const val = e.target.value;
            if (/^#[0-9A-Fa-f]{0,6}$/.test(val)) {
              onChange(val);
            }
          }}
          className="w-full bg-[var(--surface-solid)] border border-[var(--glass-border)] rounded-lg px-2 py-1.5 text-[10px] font-mono text-[var(--text-primary)] uppercase focus:border-[var(--persona-primary)]/50 outline-none transition-colors"
          maxLength={7}
        />
      </div>

      <style>{`
        @keyframes pickerFadeIn {
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
        input[type="range"] {
          -webkit-appearance: none;
          background: transparent;
        }
        input[type="range"]::-webkit-slider-thumb {
          -webkit-appearance: none;
          width: 12px;
          height: 12px;
          background: #fff;
          border-radius: 50%;
          cursor: pointer;
          box-shadow: 0 1px 4px rgba(0,0,0,0.3);
          margin-top: -3.5px;
          border: 1px solid rgba(0,0,0,0.1);
        }
        input[type="range"]::-webkit-slider-runnable-track {
          width: 100%;
          height: 5px;
          border-radius: 3px;
        }
      `}</style>
    </div>
  );
};
