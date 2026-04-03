import React, { useState, useEffect, DragEvent } from 'react';
import { useT } from '@/stores/i18n-store';
import { FileText, Scroll, Book, ExternalLink, Folder, Trash2 } from 'lucide-react';


interface PersonaFileInfo {
    name: string;
    path: string;
    exists: boolean;
    sizeBytes?: number;
}

interface PersonaFilesProps {
    personaName: string;
    basePath: string; // e.g. "data/personas/ahri"
}

/**
 * Panel that shows the key files for a persona:
 * - persona.md (identity/system prompt)
 * - memory.json (legacy memory)
 * - knowledge/memoria_legada.md
 * - knowledge/ folder (count of knowledge files)
 *
 * Each file can be: opened in the OS default app, or replaced by dragging a new file.
 */
export function PersonaFilesPanel({ personaName, basePath }: PersonaFilesProps) {
    const t = useT();
    const [files, setFiles] = useState<PersonaFileInfo[]>([]);
    const [knowledgeCount, setKnowledgeCount] = useState(0);
    const [draggingFile, setDraggingFile] = useState<string | null>(null);
    const [isElectron, setIsElectron] = useState(false);

    useEffect(() => {
        setIsElectron(!!window.ahri?.isElectron);
        loadFileInfo();
    }, [personaName]);

    const loadFileInfo = async () => {
        if (!window.ahri?.agent) return;

        const agent = window.ahri.agent;
        let personaDir = basePath;

        // Read Electron status directly — isElectron state may not have committed yet
        // (React state updates are async; calling loadFileInfo() right after setIsElectron()
        // in the same useEffect would still see the old false value)
        if (!!window.ahri?.isElectron) {
            try {
                const paths = await agent.getPaths();
                // Ensure we use the correct absolute path for the persona
                // If basePath was passed as relative (e.g. data/personas/ahri), try to map it
                // Or just trust perosnaName prop
                if (paths.personas) {
                    personaDir = `${paths.personas}/${personaName}`;
                    // Normalize slashes for Windows if needed, though shell/fs usually handle forward slashes ok in JS
                    // But let's be safe and let the backend/electron handle it or assume forward slashes work (they do in Node)
                }
            } catch (e) {
                console.warn('Failed to resolve paths:', e);
            }
        } else {
            // Web mode - use relative base
            personaDir = basePath;
        }

        const keyFiles = [
            { name: 'persona.md', path: `${personaDir}/persona.md`, label: 'persona.persona_md' as const },
            { name: 'memoria_legada.md', path: `${personaDir}/knowledge/memoria_legada.md`, label: 'persona.legacy_memory' as const },
        ];

        const loaded: PersonaFileInfo[] = [];

        for (const kf of keyFiles) {
            try {
                const content = await agent.readFile(kf.path);
                const sizeBytes = new Blob([content]).size;
                loaded.push({
                    name: kf.name,
                    path: kf.path,
                    exists: true,
                    sizeBytes,
                });
            } catch {
                loaded.push({
                    name: kf.name,
                    path: kf.path,
                    exists: false,
                });
            }
        }

        setFiles(loaded);

        // Count knowledge files
        try {
            const knowledgeFiles = await agent.listDir(`${personaDir}/knowledge`);
            // Filter .md files only
            const mdFiles = knowledgeFiles.filter((f: string) => f.endsWith('.md'));
            setKnowledgeCount(mdFiles.length);
        } catch {
            setKnowledgeCount(0);
        }
    };

    const handleOpenFile = async (path: string) => {
        if (window.ahri?.agent) {
            await window.ahri.agent.openFile(path);
        }
    };

    const handleRemoveFile = async (file: PersonaFileInfo) => {
        if (!isElectron || !file.exists) return;
        
        const confirmed = confirm(`Tem certeza que deseja remover o arquivo ${file.name}? Esta ação não pode ser desfeita.`);
        if (!confirmed) return;

        try {
            if (window.ahri?.agent) {
                await window.ahri.agent.deleteFile(file.path);
            }
            // Refresh list
            loadFileInfo();
        } catch (error) {
            console.error('Failed to remove file:', error);
            alert('Falha ao remover o arquivo.');
        }
    };

    const handleOpenFolder = async () => {
        if (window.ahri?.agent) {
            await window.ahri.agent.openFile(basePath);
        }
    };

    const handleDragEnter = (e: DragEvent, fileName: string) => {
        e.preventDefault();
        e.stopPropagation();
        setDraggingFile(fileName);
    };

    const handleDragLeave = (e: DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDraggingFile(null);
    };

    const handleDragOver = (e: DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
    };

    const handleDrop = (e: DragEvent, targetFileName: string) => {
        e.preventDefault();
        e.stopPropagation();
        setDraggingFile(null);

        const droppedFiles = e.dataTransfer.files;
        if (droppedFiles.length > 0) {
            const file = droppedFiles[0];
            // Validate file type
            const validExtensions = targetFileName.endsWith('.json')
                ? ['.json']
                : ['.md', '.txt'];

            const ext = '.' + file.name.split('.').pop()?.toLowerCase();
            if (!validExtensions.includes(ext)) {
                alert(`Please drop a ${validExtensions.join(' or ')} file`);
                return;
            }

            // Read and save the file
            const reader = new FileReader();
            reader.onload = async () => {
                const content = reader.result as string;
                console.log(`[PersonaFiles] Replacing ${targetFileName} with ${file.name} (${content.length} bytes)`);

                const targetFileInfo = files.find(f => f.name === targetFileName);
                if (!targetFileInfo) {
                    console.error('Target file info not found');
                    return;
                }
                const filePath = targetFileInfo.path;

                try {
                    if (window.ahri?.agent) {
                        await window.ahri.agent.writeFile(filePath, content);
                        alert(`File updated: ${targetFileName}`);
                    } else {
                        console.warn('Agent API not available');
                    }
                } catch (err) {
                    console.error('Failed to write file:', err);
                    alert('Failed to save file');
                }

                await loadFileInfo();
            };
            reader.readAsText(file);
        }
    };

    const formatSize = (bytes?: number) => {
        if (!bytes) return '';
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    const fileDescriptions: Record<string, { label: string; desc: string; icon: React.ReactNode }> = {
        'persona.md': {
            label: t('persona.persona_md'),
            desc: t('persona.persona_md_desc'),
            icon: <FileText size={18} />,
        },
        'memoria_legada.md': {
            label: t('persona.legacy_memory'),
            desc: t('persona.legacy_memory_desc'),
            icon: <Scroll size={18} />,
        },
    };

    return (
        <div className="space-y-4">
            {/* Key persona files */}
            {files.map((file) => {
                const info = fileDescriptions[file.name] || { label: file.name, desc: '', icon: <FileText size={18} /> };
                const isDragging = draggingFile === file.name;

                return (
                    <div
                        key={file.name}
                        className={`persona-file-card ${isDragging ? 'dragging' : ''} ${!file.exists ? 'missing' : ''}`}
                        onDragEnter={(e) => handleDragEnter(e, file.name)}
                        onDragLeave={handleDragLeave}
                        onDragOver={handleDragOver}
                        onDrop={(e) => handleDrop(e, file.name)}
                    >
                        <div className="flex items-start gap-3">
                            <span className="flex-shrink-0 mt-1" style={{ color: 'var(--persona-primary)' }}>{info.icon}</span>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                    <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                                        {info.label}
                                    </p>
                                    {file.exists && (
                                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--button-bg)', color: 'var(--text-tertiary)' }}>
                                            {formatSize(file.sizeBytes)}
                                        </span>
                                    )}
                                    {!file.exists && (
                                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-500 border border-amber-500/20">
                                            {t('persona.no_file')}
                                        </span>
                                    )}
                                </div>
                                <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                                    {info.desc}
                                </p>

                            </div>

                            {/* Actions */}
                            <div className="flex flex-row items-center gap-2 flex-shrink-0">
                                {file.exists && isElectron && (
                                    <button
                                        onClick={() => handleOpenFile(file.path)}
                                        className="persona-file-action-btn"
                                        title={t('persona.open_file')}
                                    >
                                        <ExternalLink size={14} />
                                        <span className="text-[10px]">{t('persona.open_file')}</span>
                                    </button>
                                )}

                                {isElectron && file.exists && (
                                    <button
                                        onClick={() => handleRemoveFile(file)}
                                        className="persona-file-action-btn text-red-100 hover:text-red-500 hover:bg-red-500/10"
                                        title="Remover"
                                    >
                                        <Trash2 size={14} />
                                        <span className="text-[10px]">Remover</span>
                                    </button>
                                )}
                            </div>
                        </div>

                        {/* Drag overlay */}
                        {isDragging && (
                            <div className="persona-file-drag-overlay">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                                    <polyline points="17 8 12 3 7 8" />
                                    <line x1="12" y1="3" x2="12" y2="15" />
                                </svg>
                                <p className="text-xs font-medium">{t('persona.replace_file')}</p>
                            </div>
                        )}

                        {/* Drop hint */}
                        {!isDragging && (
                            <p className="text-[10px] mt-2 font-mono" style={{ color: 'var(--text-tertiary)', opacity: 0.5 }}>
                                {t('persona.replace_file')}
                            </p>
                        )}
                    </div>
                );
            })}

            {/* Knowledge folder card */}
            <div className="persona-file-card">
                <div className="flex items-start gap-3">
                    <span className="flex-shrink-0 mt-1" style={{ color: 'var(--persona-primary)' }}><Book size={18} /></span>
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                                {t('persona.knowledge')}
                            </p>
                            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--button-bg)', color: 'var(--text-tertiary)' }}>
                                {knowledgeCount} {t('persona.knowledge_count')}
                            </span>
                        </div>
                        <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                            {t('persona.knowledge_desc')}
                        </p>
                    </div>

                    <div className="flex flex-row items-center gap-2 flex-shrink-0">
                        {isElectron && (
                            <button
                                onClick={handleOpenFolder}
                                className="persona-file-action-btn"
                                title={t('persona.open_folder')}
                            >
                                <Folder size={14} />
                                <span className="text-[10px]">{t('persona.open_folder')}</span>
                            </button>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
