import React, { useState, useEffect } from 'react';
import Editor from '@monaco-editor/react';
import { 
  Folder, File, FileText, FileCode, Settings, 
  Save, X, Plus, Copy, Trash2, Download, 
  FolderOpen, ChevronRight, RefreshCw, Eye, Edit
} from 'lucide-react';

interface FileItem {
  name: string;
  path: string;
  type: 'file' | 'directory';
  size: number;
  modified: string;
  extension: string | null;
}

interface OpenFile {
  path: string;
  content: string;
  original: string;
  modified: boolean;
}

const FileManager: React.FC = () => {
  const [currentPath, setCurrentPath] = useState('/');
  const [items, setItems] = useState<FileItem[]>([]);
  const [openFiles, setOpenFiles] = useState<OpenFile[]>([]);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  
  useEffect(() => {
    browseDirectory(currentPath);
  }, [currentPath]);

  const browseDirectory = async (path: string) => {
    try {
      setLoading(true);
      const response = await fetch(`/api/files/browse?path=${encodeURIComponent(path.slice(1))}`);
      if (response.ok) {
        const data = await response.json();
        setItems(data.items);
      } else {
        throw new Error('Failed to browse directory');
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message });
    } finally {
      setLoading(false);
    }
  };

  const openFile = async (filePath: string) => {
    // Check if already open
    const existing = openFiles.find(f => f.path === filePath);
    if (existing) {
      setActiveTab(filePath);
      return;
    }

    try {
      const response = await fetch(`/api/files/read?path=${encodeURIComponent(filePath.slice(1))}`);
      if (response.ok) {
        const data = await response.json();
        const newFile: OpenFile = {
          path: filePath,
          content: data.content,
          original: data.content,
          modified: false
        };
        setOpenFiles([...openFiles, newFile]);
        setActiveTab(filePath);
      } else {
        const error = await response.json();
        setMessage({ type: 'error', text: error.detail || 'Failed to open file' });
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const saveFile = async (filePath: string) => {
    const file = openFiles.find(f => f.path === filePath);
    if (!file) return;

    try {
      const response = await fetch('/api/files/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: filePath.slice(1),
          content: file.content
        })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'File saved successfully' });
        // Update original content and clear modified flag
        setOpenFiles(openFiles.map(f =>
          f.path === filePath
            ? { ...f, original: f.content, modified: false }
            : f
        ));
        // Refresh directory view
        browseDirectory(currentPath);
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to save file');
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const closeFile = (filePath: string) => {
    const file = openFiles.find(f => f.path === filePath);
    if (file?.modified) {
      if (!confirm(`${file.path} has unsaved changes. Close anyway?`)) {
        return;
      }
    }

    const newOpenFiles = openFiles.filter(f => f.path !== filePath);
    setOpenFiles(newOpenFiles);

    if (activeTab === filePath) {
      setActiveTab(newOpenFiles.length > 0 ? newOpenFiles[0].path : null);
    }
  };

  const updateFileContent = (filePath: string, content: string) => {
    setOpenFiles(openFiles.map(f =>
      f.path === filePath
        ? { ...f, content, modified: content !== f.original }
        : f
    ));
  };

  const deleteFile = async (filePath: string) => {
    if (!confirm(`Delete ${filePath}? This cannot be undone.`)) {
      return;
    }

    try {
      const response = await fetch(`/api/files/delete?path=${encodeURIComponent(filePath.slice(1))}`, {
        method: 'DELETE'
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'Deleted successfully' });
        // Close if open
        setOpenFiles(openFiles.filter(f => f.path !== filePath));
        // Refresh directory
        browseDirectory(currentPath);
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to delete');
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const createNewFile = async () => {
    const fileName = prompt('Enter file name (e.g., mypool_driver.py):');
    if (!fileName) return;

    const newPath = `${currentPath}${currentPath.endsWith('/') ? '' : '/'}${fileName}`;

    try {
      const response = await fetch('/api/files/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: newPath.slice(1),
          content: ''
        })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'File created successfully' });
        browseDirectory(currentPath);
        // Open the new file
        openFile(newPath);
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create file');
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const copyFile = async (filePath: string) => {
    const fileName = filePath.split('/').pop();
    const newName = prompt(`Copy ${fileName} as:`, `${fileName}.copy`);
    if (!newName) return;

    const dir = filePath.substring(0, filePath.lastIndexOf('/'));
    const newPath = `${dir}/${newName}`;

    try {
      const response = await fetch('/api/files/copy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: filePath.slice(1),
          new_path: newPath.slice(1)
        })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'File copied successfully' });
        browseDirectory(currentPath);
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to copy file');
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const downloadFile = (filePath: string) => {
    const url = `/api/files/download?path=${encodeURIComponent(filePath.slice(1))}`;
    window.open(url, '_blank');
  };

  const renameFile = async (filePath: string) => {
    const fileName = filePath.split('/').pop();
    const newName = prompt(`Rename "${fileName}" to:`, fileName);
    if (!newName || newName === fileName) return;

    const dir = filePath.substring(0, filePath.lastIndexOf('/'));
    const newPath = `${dir}/${newName}`;

    try {
      const response = await fetch('/api/files/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: filePath.slice(1),
          new_path: newPath.slice(1)
        })
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'File renamed successfully' });
        // Update open files if the renamed file is open
        if (openFiles.some(f => f.path === filePath)) {
          setOpenFiles(openFiles.map(f =>
            f.path === filePath ? { ...f, path: newPath } : f
          ));
          if (activeTab === filePath) {
            setActiveTab(newPath);
          }
        }
        // Refresh directory
        browseDirectory(currentPath);
      } else {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to rename file');
      }
    } catch (error: any) {
      setMessage({ type: 'error', text: error.message });
    }
  };

  const getFileIcon = (item: FileItem) => {
    if (item.type === 'directory') {
      return <Folder className="w-5 h-5 text-blue-400" />;
    }

    switch (item.extension) {
      case '.py':
        return <FileCode className="w-5 h-5 text-green-400" />;
      case '.yaml':
      case '.yml':
        return <Settings className="w-5 h-5 text-purple-400" />;
      case '.json':
        return <FileCode className="w-5 h-5 text-yellow-400" />;
      case '.md':
        return <FileText className="w-5 h-5 text-gray-400" />;
      default:
        return <File className="w-5 h-5 text-gray-400" />;
    }
  };

  const getLanguage = (filePath: string): string => {
    const ext = filePath.split('.').pop()?.toLowerCase();
    const languageMap: Record<string, string> = {
      'py': 'python',
      'js': 'javascript',
      'ts': 'typescript',
      'json': 'json',
      'yaml': 'yaml',
      'yml': 'yaml',
      'md': 'markdown',
      'sh': 'shell',
      'txt': 'plaintext',
      'log': 'plaintext'
    };
    return languageMap[ext || ''] || 'plaintext';
  };

  const isReadOnly = (filePath: string): boolean => {
    return filePath.endsWith('.example');
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const breadcrumbs = currentPath.split('/').filter(Boolean);
  const activeFile = openFiles.find(f => f.path === activeTab);

  return (
    <div className="flex flex-col h-screen bg-gray-950">
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <h1 className="text-2xl font-bold text-gray-100">File Manager</h1>
        <p className="text-sm text-gray-400 mt-1">Browse and edit configuration files</p>
      </div>

      {/* Message Banner */}
      {message && (
        <div className={`mx-4 mt-4 p-3 rounded-md ${message.type === 'success' ? 'bg-green-900/40 border border-green-700' : 'bg-red-900/40 border border-red-700'}`}>
          <div className="flex items-center justify-between">
            <p className={`text-sm ${message.type === 'success' ? 'text-green-200' : 'text-red-200'}`}>
              {message.text}
            </p>
            <button onClick={() => setMessage(null)} className="text-gray-400 hover:text-gray-300">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* File Browser Sidebar */}
        <div className="w-80 border-r border-gray-800 flex flex-col bg-gray-900/40">
          {/* Breadcrumbs */}
          <div className="p-3 border-b border-gray-800 flex items-center space-x-2 text-sm">
            <button
              onClick={() => setCurrentPath('/')}
              className="text-blue-400 hover:text-blue-300"
            >
              /config
            </button>
            {breadcrumbs.map((crumb, idx) => (
              <React.Fragment key={idx}>
                <ChevronRight className="w-4 h-4 text-gray-600" />
                <button
                  onClick={() => setCurrentPath('/' + breadcrumbs.slice(0, idx + 1).join('/'))}
                  className="text-blue-400 hover:text-blue-300"
                >
                  {crumb}
                </button>
              </React.Fragment>
            ))}
          </div>

          {/* Toolbar */}
          <div className="p-2 border-b border-gray-800 flex items-center space-x-2">
            <button
              onClick={createNewFile}
              className="p-2 rounded hover:bg-gray-800 text-gray-300 hover:text-gray-100"
              title="New File"
            >
              <Plus className="w-4 h-4" />
            </button>
            <button
              onClick={() => browseDirectory(currentPath)}
              className="p-2 rounded hover:bg-gray-800 text-gray-300 hover:text-gray-100"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* File List */}
          <div className="flex-1 overflow-y-auto">
            {loading && items.length === 0 ? (
              <div className="p-4 text-center text-gray-500">
                <RefreshCw className="w-6 h-6 mx-auto animate-spin mb-2" />
                Loading...
              </div>
            ) : items.length === 0 ? (
              <div className="p-4 text-center text-gray-500">
                <FolderOpen className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>Empty directory</p>
              </div>
            ) : (
              <div className="divide-y divide-gray-800">
                {/* Parent directory */}
                {currentPath !== '/' && (
                  <div
                    onClick={() => {
                      const parentPath = currentPath.substring(0, currentPath.lastIndexOf('/')) || '/';
                      setCurrentPath(parentPath);
                    }}
                    className="px-3 py-2 hover:bg-gray-800 cursor-pointer flex items-center space-x-3"
                  >
                    <Folder className="w-5 h-5 text-gray-500" />
                    <span className="text-gray-400">..</span>
                  </div>
                )}

                {/* Items */}
                {items.map((item) => (
                  <div
                    key={item.path}
                    className="px-3 py-2 hover:bg-gray-800 cursor-pointer flex items-center justify-between group"
                  >
                    <div
                      onClick={() => {
                        if (item.type === 'directory') {
                          setCurrentPath(item.path);
                        } else {
                          openFile(item.path);
                        }
                      }}
                      className="flex items-center space-x-3 flex-1"
                    >
                      {getFileIcon(item)}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-200 truncate">{item.name}</p>
                        <p className="text-xs text-gray-500">
                          {item.type === 'file' ? formatSize(item.size) : 'Folder'}
                        </p>
                      </div>
                    </div>

                    {item.type === 'file' && (
                      <div className="flex items-center space-x-1 opacity-0 group-hover:opacity-100">
                        <button
                          onClick={(e) => { e.stopPropagation(); renameFile(item.path); }}
                          className="p-1 rounded hover:bg-gray-700 text-gray-400 hover:text-gray-200"
                          title="Rename"
                        >
                          <Edit className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); copyFile(item.path); }}
                          className="p-1 rounded hover:bg-gray-700 text-gray-400 hover:text-gray-200"
                          title="Copy"
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); downloadFile(item.path); }}
                          className="p-1 rounded hover:bg-gray-700 text-gray-400 hover:text-gray-200"
                          title="Download"
                        >
                          <Download className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); deleteFile(item.path); }}
                          className="p-1 rounded hover:bg-gray-700 text-red-400 hover:text-red-300"
                          title="Delete"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Editor Area */}
        <div className="flex-1 flex flex-col">
          {openFiles.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              <div className="text-center">
                <FileText className="w-16 h-16 mx-auto mb-4 opacity-50" />
                <p className="text-lg">No files open</p>
                <p className="text-sm mt-2">Select a file from the sidebar to start editing</p>
              </div>
            </div>
          ) : (
            <>
              {/* Tabs */}
              <div className="flex items-center border-b border-gray-800 bg-gray-900/40 overflow-x-auto">
                {openFiles.map((file) => (
                  <div
                    key={file.path}
                    onClick={() => setActiveTab(file.path)}
                    className={`flex items-center space-x-2 px-4 py-2 border-r border-gray-800 cursor-pointer ${
                      activeTab === file.path
                        ? 'bg-gray-900 text-gray-100'
                        : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
                    }`}
                  >
                    <span className="text-sm truncate max-w-xs">
                      {file.path.split('/').pop()}
                      {file.modified && ' •'}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        closeFile(file.path);
                      }}
                      className="hover:bg-gray-700 rounded p-0.5"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>

              {/* Editor */}
              {activeFile && (
                <>
                  <div className="p-2 border-b border-gray-800 flex items-center justify-between bg-gray-900/40">
                    <div className="flex items-center space-x-2">
                      <span className="text-sm text-gray-400">{activeFile.path}</span>
                      {isReadOnly(activeFile.path) && (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs bg-yellow-900/40 text-yellow-400 border border-yellow-700">
                          <Eye className="w-3 h-3 mr-1" />
                          Read-only
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => saveFile(activeFile.path)}
                      disabled={!activeFile.modified || isReadOnly(activeFile.path)}
                      className={`inline-flex items-center px-3 py-1 rounded text-sm ${
                        activeFile.modified && !isReadOnly(activeFile.path)
                          ? 'bg-blue-600 text-white hover:bg-blue-700'
                          : 'bg-gray-800 text-gray-500 cursor-not-allowed'
                      }`}
                      title={isReadOnly(activeFile.path) ? 'File is read-only (view only)' : ''}
                    >
                      <Save className="w-4 h-4 mr-1" />
                      Save
                    </button>
                  </div>

                  <div className="flex-1">
                    <Editor
                      height="100%"
                      language={getLanguage(activeFile.path)}
                      value={activeFile.content}
                      onChange={(value) => updateFileContent(activeFile.path, value || '')}
                      theme="vs-dark"
                      options={{
                        minimap: { enabled: true },
                        fontSize: 14,
                        lineNumbers: 'on',
                        rulers: [80, 120],
                        wordWrap: 'off',
                        automaticLayout: true,
                        readOnly: isReadOnly(activeFile.path)
                      }}
                    />
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default FileManager;
