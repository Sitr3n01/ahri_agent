import { useState, useRef, DragEvent } from 'react';

interface ImageUploadProps {
  label: string;
  currentImage: string;
  onImageSelect: (file: File) => void;
  previewShape?: 'circle' | 'rectangle';
  previewSize?: { width: number; height: number };
}

export function ImageUpload({
  label,
  currentImage,
  onImageSelect,
  previewShape = 'circle',
  previewSize = { width: 64, height: 64 },
}: ImageUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragEnter = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      if (file.type.startsWith('image/')) {
        onImageSelect(file);
      } else {
        alert('Please upload an image file (PNG, JPG, WEBP)');
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      onImageSelect(files[0]);
    }
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div>
      <label className="block text-xs font-mono mb-2" style={{ color: 'var(--text-tertiary)' }}>
        {label}
      </label>
      <div className="flex items-start gap-6">
        {/* Preview Area (Fixed width for alignment) */}
        <div className="w-32 sm:w-40 flex-shrink-0">
          <div
            className={`
              overflow-hidden border-2 mx-auto
              ${previewShape === 'circle' ? 'rounded-full' : 'rounded-xl'}
            `}
            style={{ width: previewSize.width, height: previewSize.height, borderColor: 'var(--glass-border)' }}
          >
            <img
              src={`/${currentImage}`}
              alt="Preview"
              className="w-full h-full object-cover"
            />
          </div>
        </div>

        {/* Upload Area */}
        <div
          className={`
            flex-1 border-2 border-dashed rounded-sm p-4 transition-all cursor-pointer
            ${isDragging
              ? 'border-purple-400 bg-purple-400/10'
              : ''
            }
          `}
          style={!isDragging ? { borderColor: 'var(--glass-border)' } : undefined}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onClick={handleClick}
          onMouseEnter={(e) => { if (!isDragging) { e.currentTarget.style.borderColor = 'var(--border-medium)'; e.currentTarget.style.background = 'var(--surface-hover)'; } }}
          onMouseLeave={(e) => { if (!isDragging) { e.currentTarget.style.borderColor = 'var(--glass-border)'; e.currentTarget.style.background = 'transparent'; } }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/jpg,image/webp"
            onChange={handleFileSelect}
            className="hidden"
          />
          <div className="text-center">
            <svg
              className="mx-auto mb-2"
              style={{ color: 'var(--text-tertiary)' }}
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            <p className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
              {isDragging ? 'Drop image here' : 'Click or drag image'}
            </p>
            <p className="text-xs font-mono mt-1" style={{ color: 'var(--text-tertiary)' }}>
              PNG, JPG, WEBP
            </p>
          </div>
        </div>
      </div>
      <p className="text-xs mt-1 font-mono" style={{ color: 'var(--text-tertiary)' }}>
        Current: {currentImage}
      </p>
    </div>
  );
}
