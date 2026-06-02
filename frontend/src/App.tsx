/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Plus,
  Library,
  MessageSquare,
  Image as ImageIcon,
  FileText,
  PanelLeftClose,
  PanelLeftOpen,
  HelpCircle,
  Sparkles,
  Crown,
  ChevronDown,
  LayoutGrid,
  ArrowRight,
  CheckCircle2,
  Clock,
  Palette,
  Settings2,
  ChevronLeft,
  Send,
  X,
  Lightbulb,
  Clapperboard,
  Users,
  MapPin,
  Package,
  Loader2,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import {
  sendChat,
  submitConfig,
  streamSSE,
  createEpisodeFromScript,
  generateStoryboards,
  generateAigc,
  getEpisodeStoryboardMedia,
  mergeEpisodeVideos,
  saveEpisodeManualEdits,
  cancelStoryboardTask,
  getStoryboardTaskStatus,
  getThread,
  type AsyncTaskStatusResponse,
  type CharacterImageItem,
  type ChatResponse,
  type ThreadDetailResponse,
  type ThreadListItem,
  type SaveManualEditsRequest,
  type SSEEvent,
  type StoryboardMediaItem,
  updateThreadState,
  listThreads,
} from './services/api';
import ScriptView from './components/ScriptView';
import type { ScriptData } from './components/ScriptView';
import StoryEditorPage from './story-editor/StoryEditorPage';

type MessageType =
  | 'text'
  | 'tool-call'
  | 'action-card'
  | 'config-form'
  | 'user'
  | 'storyboard-card'
  | 'video-progress-card'
  | 'script-card';

interface ToolStep {
  label: string;
  status: 'completed' | 'loading' | 'pending';
  detail?: string;
}

function parseShotDuration(value: string | undefined): number {
  const text = String(value || '').trim().toLowerCase().replace('秒', '').replace('s', '');
  const parsed = Number(text);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
}

function formatScriptDuration(script?: ScriptData | null): string {
  if (!script) return '--';
  const derived = (script.shots || []).reduce((sum, shot) => sum + parseShotDuration(shot.duration), 0);
  if (derived > 0) {
    return `${derived.toFixed(1)} 秒`;
  }
  return script.totalDuration || '--';
}

const NODE_DISPLAY_MAP: Record<string, string> = {
  intent_analysis:   '设置意图和更新配置参数',
  breakdown:         '进行剧本生成',
  analysis_report:   '进行剧本生成',
  reverse_engineer:  '进行剧本生成',
  move_plan:         '进行剧本生成',
  writing:           '进行剧本生成',
  verify:            '进行剧本生成',
  v2_preprocess:     '进行剧本生成',
  v2_analyst:        '进行剧本生成',
  v2_normalizer:     '进行剧本生成',
  v2_entity_mapper:  '进行剧本生成',
  v2_creator:        '进行剧本生成',
  proofread:         '剧本审核与润色',
  v2_qc:             '剧本审核与润色',
  load_reference:    '信息更新',
  external_enrichment: '外部热点补充',
  plan_story:        '剧本规划',
  write_scenes:      '剧本生成',
  finalize:          '剧本生成',
};

// 每个展示分组的"终结节点"——只有该节点 node_end 时才标记步骤完成
const GROUP_TERMINAL_NODES: Record<string, Set<string>> = {
  '设置意图和更新配置参数': new Set(['intent_analysis']),
  '进行剧本生成':         new Set(['verify', 'v2_creator']),
  '剧本审核与润色':       new Set(['proofread', 'v2_qc']),
  '信息更新':             new Set(['load_reference']),
  '外部热点补充':         new Set(['external_enrichment']),
  '剧本规划':             new Set(['plan_story']),
  '剧本生成':             new Set(['finalize']),
};

interface ConfigOption {
  label: string;
  value: string;
}

interface ConfigSection {
  id: string;
  label: string;
  options: ConfigOption[];
}

interface Message {
  id: string;
  type: MessageType;
  content?: string;
  sender: 'ai' | 'user';
  timestamp: string;
  toolSteps?: ToolStep[];
  configData?: {
    threadId: string;
    title: string;
    sections: ConfigSection[];
    defaults: Record<string, string>;
  };
  cardData?: {
    title: string;
    description: string;
    duration?: string;
    style?: string;
    type?: string;
    state?: 'loading' | 'completed' | 'failed';
    progress?: number;
    taskMessage?: string;
    error?: string;
    taskId?: string;
    episodeId?: number;
    sourceStoryboardMsgId?: string;
    videoState?: 'idle' | 'loading' | 'completed' | 'failed';
    videoProgress?: number;
    videoTaskId?: string;
    videoTaskMessage?: string;
    videoError?: string;
    videoSummary?: string;
    mergedVideoUrl?: string;
    actions: { label: string; primary?: boolean }[];
    icon?: React.ReactNode;
    stats?: { label: string; value: string; icon: React.ReactNode }[];
  };
}

interface StoryEditorPersistState {
  activeShotId: number;
  activeFrameByShotId: Record<number, string>;
  activeView: 'storyboard' | 'roles';
}

const VIDEO_GENERATION_CANCEL_MESSAGE = '视频生成已取消';

const IMAGE_UPLOAD_TYPES = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
  'image/gif',
]);

const DOC_UPLOAD_TYPES = new Set([
  'application/pdf',
  'application/msword',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
]);

const IMAGE_UPLOAD_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.webp', '.gif'];
const DOC_UPLOAD_EXTENSIONS = ['.pdf', '.doc', '.docx', '.txt', '.md'];

const FILE_INPUT_ACCEPT = [
  ...IMAGE_UPLOAD_EXTENSIONS,
  ...DOC_UPLOAD_EXTENSIONS,
].join(',');

function nowTimestamp(): string {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function getFileKey(file: File): string {
  return `${file.name}_${file.size}_${file.lastModified}`;
}

function getMessageIcon(type: Message['type']) {
  if (type === 'storyboard-card' || type === 'video-progress-card') {
    return <Clapperboard size={18} />;
  }
  return undefined;
}

function sanitizeMessage(message: Message): Record<string, unknown> {
  return {
    ...message,
    cardData: message.cardData
      ? {
          ...message.cardData,
          icon: undefined,
          stats: message.cardData.stats?.map((stat) => ({
            label: stat.label,
            value: stat.value,
          })),
        }
      : undefined,
  };
}

function restoreMessage(raw: Record<string, unknown>): Message {
  const next = raw as unknown as Message;
  return {
    ...next,
    cardData: next.cardData
      ? {
          ...next.cardData,
          icon: getMessageIcon(next.type),
          stats: next.cardData.stats?.map((stat) => ({
            ...stat,
            icon: stat.label.includes('角色')
              ? <Users size={16} />
              : stat.label.includes('场景')
                ? <MapPin size={16} />
                : stat.label.includes('道具')
                  ? <Package size={16} />
                  : <LayoutGrid size={16} />,
          })),
        }
      : undefined,
  };
}

function isSupportedUploadFile(file: File): boolean {
  const mime = (file.type || '').toLowerCase();
  if (IMAGE_UPLOAD_TYPES.has(mime) || DOC_UPLOAD_TYPES.has(mime)) {
    return true;
  }
  const lowerName = file.name.toLowerCase();
  return [...IMAGE_UPLOAD_EXTENSIONS, ...DOC_UPLOAD_EXTENSIONS].some(ext => lowerName.endsWith(ext));
}

function isImageFile(file: File): boolean {
  const mime = (file.type || '').toLowerCase();
  if (mime.startsWith('image/')) return true;
  const lowerName = file.name.toLowerCase();
  return IMAGE_UPLOAD_EXTENSIONS.some(ext => lowerName.endsWith(ext));
}

function renderScriptContent(content: string) {
  const lines = content.split('\n');
  return lines.map((line, idx) => {
    const trimmed = line.trim();

    // Skip code fences
    if (trimmed.startsWith('```')) {
      return null;
    }

    // 通用 ## 标题处理（去掉 ## 前缀，渲染为标题）
    if (trimmed.startsWith('## ')) {
      return <h3 key={idx} className="text-lg font-bold mt-4 mb-2">{trimmed.substring(3)}</h3>;
    }
    
    // 分镜项 - 匹配 - **[名称]** - 内容
    const match = trimmed.match(/^-\s*\*\*(.+?)\*\*\s*-\s*(.+)$/);
    if (match) {
      return (
        <div key={idx} className="ml-4 my-1">
          <span className="font-semibold">{match[1]}</span>
          <span className="text-gray-600"> - {match[2]}</span>
        </div>
      );
    }
    
    // 普通项 - 匹配 - 内容
    if (trimmed.startsWith('- ')) {
      return <div key={idx} className="ml-4 my-1 text-gray-700">{trimmed.substring(2)}</div>;
    }
    
    // 空行
    if (!trimmed) {
      return <br key={idx} />;
    }
    
    return <div key={idx} className="my-1 text-gray-700">{line}</div>;
  });
}

export default function App() {
  const [inputText, setInputText] = useState('');
  const [isChatMode, setIsChatMode] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [formSelections, setFormSelections] = useState<Record<string, Record<string, string>>>({});
  const [submittedForms, setSubmittedForms] = useState<Set<string>>(new Set());
  const [collapsedForms, setCollapsedForms] = useState<Set<string>>(new Set());
  const [countdowns, setCountdowns] = useState<Record<string, number>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [dismissedHints, setDismissedHints] = useState<Set<string>>(new Set());
  const [isStoryboardGenerating, setIsStoryboardGenerating] = useState(false);
  const [isVideoGenerating, setIsVideoGenerating] = useState(false);
  const [currentThreadId, setCurrentThreadId] = useState('');
  const [threadItems, setThreadItems] = useState<ThreadListItem[]>([]);
  const [isThreadsLoading, setIsThreadsLoading] = useState(false);
  const [currentUserInput, setCurrentUserInput] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState('');
  const [isScriptOpen, setIsScriptOpen] = useState(false);
  const [isStoryboardEditorOpen, setIsStoryboardEditorOpen] = useState(false);
  const [storyboardEditorEpisodeId, setStoryboardEditorEpisodeId] = useState<number | null>(null);
  const [storyboardEditorMediaItems, setStoryboardEditorMediaItems] = useState<StoryboardMediaItem[]>([]);
  const [storyboardEditorCharacterImages, setStoryboardEditorCharacterImages] = useState<CharacterImageItem[]>([]);
  const [isStoryboardEditorMediaLoading, setIsStoryboardEditorMediaLoading] = useState(false);
  const [storyEditorState, setStoryEditorState] = useState<StoryEditorPersistState>({
    activeShotId: 1,
    activeFrameByShotId: {},
    activeView: 'storyboard',
  });
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [scriptData, setScriptData] = useState<ScriptData | undefined>(undefined);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const userScrolledUp = useRef(false);
  const canceledVideoProgressCardIdsRef = useRef<Set<string>>(new Set());

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const handleScroll = () => {
    const el = scrollContainerRef.current;
    if (!el) return;
    // 距底部超过 150px 则认为用户主动上滑
    userScrolledUp.current = el.scrollHeight - el.scrollTop - el.clientHeight > 150;
  };

  useEffect(() => {
    if (isChatMode && !userScrolledUp.current) {
      scrollToBottom();
    }
  }, [messages, isChatMode]);

  useEffect(() => {
    if (isScriptOpen && !isSidebarCollapsed) {
      setIsSidebarCollapsed(true);
    }
  }, [isScriptOpen, isSidebarCollapsed]);

  useEffect(() => {
    if (!isStoryboardEditorOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsStoryboardEditorOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isStoryboardEditorOpen]);

  const resetComposerState = () => {
    setIsChatMode(false);
    setMessages([]);
    setFormSelections({});
    setSubmittedForms(new Set());
    setCollapsedForms(new Set());
    setCountdowns({});
    setCurrentThreadId('');
    setCurrentUserInput('');
    setSelectedFiles([]);
    setFileError('');
    setIsScriptOpen(false);
    setIsStoryboardEditorOpen(false);
    setStoryboardEditorEpisodeId(null);
    setStoryboardEditorMediaItems([]);
    setStoryboardEditorCharacterImages([]);
    setScriptData(undefined);
    setStoryEditorState({
      activeShotId: 1,
      activeFrameByShotId: {},
      activeView: 'storyboard',
    });
  };

  const loadThreads = async () => {
    setIsThreadsLoading(true);
    try {
      const items = await listThreads();
      setThreadItems(items);
    } catch {
      setThreadItems([]);
    } finally {
      setIsThreadsLoading(false);
    }
  };

  const openThreadDetail = async (detail: ThreadDetailResponse) => {
    setCurrentThreadId(detail.thread_id);
    const state = detail.state;
    const snapshotMessages = (state.messages_snapshot_json || []).length > 0
      ? (state.messages_snapshot_json || []).map((item) =>
          restoreMessage(item as Record<string, unknown>)
        )
      : detail.messages.map((item) =>
          restoreMessage({
            id: item.id,
            type: (item.message_type === 'user' ? 'user' : item.message_type) as Message['type'],
            sender: item.role === 'user' ? 'user' : 'ai',
            timestamp: new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            ...(item.content_json as Record<string, unknown>),
          })
        );
    setMessages(snapshotMessages);
    setIsChatMode(snapshotMessages.length > 0);
    setScriptData((state.current_script_data_json as unknown as ScriptData) || undefined);
    setStoryEditorState({
      activeShotId: Number((state.editor_state_json?.activeShotId as number) || 1),
      activeFrameByShotId: (state.editor_state_json?.activeFrameByShotId as Record<number, string>) || {},
      activeView: (state.editor_state_json?.activeView as 'storyboard' | 'roles') || 'storyboard',
    });

    const activeView = state.active_view || 'chat';
    setIsScriptOpen(activeView === 'script');
    setIsStoryboardEditorOpen(activeView === 'story-editor');

    const currentEpisodeId = Number(state.current_episode_id || detail.latest_episode_id || 0) || null;
    setStoryboardEditorEpisodeId(currentEpisodeId);

    const mediaSnapshot = state.media_snapshot_json || {};
    const snapshotItems = Array.isArray(mediaSnapshot.items)
      ? (mediaSnapshot.items as StoryboardMediaItem[])
      : [];
    const snapshotCharacters = Array.isArray(mediaSnapshot.character_images)
      ? (mediaSnapshot.character_images as CharacterImageItem[])
      : [];
    if (snapshotItems.length > 0 || snapshotCharacters.length > 0) {
      setStoryboardEditorMediaItems(snapshotItems);
      setStoryboardEditorCharacterImages(snapshotCharacters);
    } else {
      setStoryboardEditorMediaItems([]);
      setStoryboardEditorCharacterImages([]);
    }

    if (currentEpisodeId && activeView === 'story-editor') {
      setIsStoryboardEditorMediaLoading(true);
      try {
        const media = await getEpisodeStoryboardMedia(currentEpisodeId);
        setStoryboardEditorMediaItems(media.items || []);
        setStoryboardEditorCharacterImages(media.character_images || []);
      } catch {
        // keep snapshot fallback
      } finally {
        setIsStoryboardEditorMediaLoading(false);
      }
    }
  };

  useEffect(() => {
    void loadThreads();
  }, []);

  useEffect(() => {
    if (!currentThreadId) return;
    const timer = window.setTimeout(() => {
      const activeView = isStoryboardEditorOpen
        ? 'story-editor'
        : isScriptOpen
          ? 'script'
          : 'chat';
      void updateThreadState(currentThreadId, {
        active_view: activeView,
        current_episode_id: storyboardEditorEpisodeId,
        current_script_data_json: (scriptData as unknown as Record<string, unknown>) || {},
        media_snapshot_json: {
          items: storyboardEditorMediaItems,
          character_images: storyboardEditorCharacterImages,
        },
        editor_state_json: {
          activeShotId: storyEditorState.activeShotId,
          activeFrameByShotId: storyEditorState.activeFrameByShotId,
          activeView: storyEditorState.activeView,
        },
        messages_snapshot_json: messages.map(sanitizeMessage),
      }).catch(() => undefined);
    }, 800);

    return () => window.clearTimeout(timer);
  }, [
    currentThreadId,
    isScriptOpen,
    isStoryboardEditorOpen,
    storyboardEditorEpisodeId,
    storyboardEditorMediaItems,
    storyboardEditorCharacterImages,
    scriptData,
    messages,
    storyEditorState,
  ]);

  const openStoryboardEditor = async (episodeId?: number) => {
    setStoryboardEditorEpisodeId(episodeId ?? null);
    setStoryboardEditorMediaItems([]);
    setStoryboardEditorCharacterImages([]);
    setIsStoryboardEditorOpen(true);

    if (!episodeId) {
      setIsStoryboardEditorMediaLoading(false);
      return;
    }

    setIsStoryboardEditorMediaLoading(true);
    try {
      const media = await getEpisodeStoryboardMedia(episodeId);
      setStoryboardEditorMediaItems(media.items || []);
      setStoryboardEditorCharacterImages(media.character_images || []);
    } catch {
      setStoryboardEditorMediaItems([]);
      setStoryboardEditorCharacterImages([]);
    } finally {
      setIsStoryboardEditorMediaLoading(false);
    }
  };

  const handleSaveStoryboardEdits = async (payload: SaveManualEditsRequest) => {
    if (!storyboardEditorEpisodeId) {
      throw new Error('未找到可保存的剧集 ID');
    }

    await saveEpisodeManualEdits(storyboardEditorEpisodeId, payload);

    setScriptData((prev) => {
      if (!prev) return prev;

      const characterPatch = new Map(payload.characters.map((c) => [c.id, c]));
      const nextCharacters = prev.characters.map((c) => {
        const patch = characterPatch.get(c.id);
        if (!patch) return c;
        return {
          ...c,
          name: patch.name || c.name,
          voice: patch.voice || c.voice,
          appearance: {
            ...c.appearance,
            features: patch.appearance || c.appearance.features,
          },
        };
      });

      const shotPatch = new Map(payload.shots.map((s) => [s.storyboard_number, s]));
      const nextShots = prev.shots.map((s, index) => {
        const sid = Number(s.id) || (index + 1);
        const patch = shotPatch.get(sid);
        if (!patch) return s;
        return {
          ...s,
          summary: patch.summary || s.summary,
          visualDesc: patch.visual_desc || s.visualDesc,
          narration: patch.narration || '',
          hasNarration: Boolean((patch.narration || '').trim()),
          duration: patch.duration_seconds > 0 ? `${patch.duration_seconds.toFixed(1)}s` : s.duration,
        };
      });

      const nextTotalDuration = nextShots
        .reduce((sum, shot) => {
          const text = String(shot.duration || '').trim().toLowerCase().replace('秒', '').replace('s', '');
          const value = Number(text);
          return sum + (Number.isFinite(value) && value > 0 ? value : 0);
        }, 0)
        .toFixed(1);

      return {
        ...prev,
        characters: nextCharacters,
        shots: nextShots,
        totalDuration: `${nextTotalDuration} 秒`,
      };
    });
  };

  const handleOptionSelect = (msgId: string, sectionId: string, value: string) => {
    setFormSelections(prev => ({
      ...prev,
      [msgId]: {
        ...(prev[msgId] || {}),
        [sectionId]: value,
      }
    }));
  };

  const toggleFormCollapse = (msgId: string) => {
    setCollapsedForms(prev => {
      const newSet = new Set(prev);
      if (newSet.has(msgId)) {
        newSet.delete(msgId);
      } else {
        newSet.add(msgId);
      }
      return newSet;
    });
  };

  const getSelectedValue = (msgId: string, sectionId: string, defaultValue: string): string => {
    return formSelections[msgId]?.[sectionId] ?? defaultValue;
  };

  const handleConfigSubmit = async (msgId: string, configData: NonNullable<Message['configData']>) => {
    if (submittedForms.has(msgId)) return;

    // Lock the form and clear countdown
    setSubmittedForms(prev => new Set(prev).add(msgId));
    setCountdowns(prev => {
      const next = { ...prev };
      delete next[msgId];
      return next;
    });

    // Build selections from formSelections (fall back to defaults)
    const selections: Record<string, string> = {};
    for (const section of configData.sections) {
      selections[section.id] = getSelectedValue(msgId, section.id, configData.defaults[section.id] || '');
    }

    // Insert a "confirmed config" user message
    const confirmMsg: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: '我已确认配置',
      sender: 'user',
      timestamp: nowTimestamp(),
    };
    setMessages(prev => [...prev, confirmMsg]);

    // Insert a tool-call message that will update as SSE streams in
    const toolMsgId = (Date.now() + 1).toString();
    const toolMsg: Message = {
      id: toolMsgId,
      type: 'tool-call',
      sender: 'ai',
      timestamp: nowTimestamp(),
      toolSteps: [],
    };
    setMessages(prev => [...prev, toolMsg]);

    try {
      const response = await submitConfig(configData.threadId, currentUserInput, selections);

      const steps: ToolStep[] = [];
      let finalContent = '';

      const updateToolSteps = () => {
        setMessages(prev =>
          prev.map(m =>
            m.id === toolMsgId ? { ...m, toolSteps: [...steps] } : m
          )
        );
      };

      streamSSE(
        response,
        (event: SSEEvent) => {
          if (event.type === 'node_start') {
            const nodeName = event.node || '';
            const displayLabel = NODE_DISPLAY_MAP[nodeName];
            // simple_chat 及未映射的节点不展示步骤
            if (!displayLabel) return;

            const existing = steps.find(s => s.label === displayLabel);
            if (!existing) {
              steps.push({ label: displayLabel, status: 'loading' });
            } else if (existing.status === 'completed') {
              // 该分组已标记完成但又有新节点进入（如迭代重跑）
              existing.status = 'loading';
            }
            updateToolSteps();
          } else if (event.type === 'node_end') {
            const nodeName = event.node || '';
            const displayLabel = NODE_DISPLAY_MAP[nodeName];

            if (!displayLabel) return;

            // 只在该分组的终结节点完成时才标记步骤 completed
            const terminals = GROUP_TERMINAL_NODES[displayLabel];
            if (terminals?.has(nodeName)) {
              const idx = steps.findIndex(s => s.label === displayLabel);
              if (idx !== -1) {
                steps[idx] = { ...steps[idx], status: 'completed' };
              }
            }
            updateToolSteps();
          } else if (event.type === 'token' && event.content) {
            finalContent += event.content;
            setMessages(prev => {
              const lastMsg = prev[prev.length - 1];
              if (lastMsg && lastMsg.type === 'text' && lastMsg.id.startsWith('stream-')) {
                return prev.map(m =>
                  m.id === lastMsg.id
                    ? { ...m, content: (m.content || '') + event.content }
                    : m
                );
              }
              return [
                ...prev,
                {
                  id: `stream-${Date.now()}`,
                  type: 'text' as MessageType,
                  content: event.content || '',
                  sender: 'ai' as const,
                  timestamp: nowTimestamp(),
                },
              ];
            });
          } else if (event.type === 'done') {
            // 设置结构化数据
            if (event.script_data) {
              setScriptData(event.script_data);
            }
            // done 事件包含最终内容（可能是全量或增量）
            // 如果之前已有 token 流式内容，done 的 content 就是全量，不要重复追加
            if (event.content && !finalContent) {
              finalContent = event.content;
              setMessages(prev => {
                const lastMsg = prev[prev.length - 1];
                if (lastMsg && lastMsg.type === 'text' && lastMsg.id.startsWith('stream-')) {
                  return prev.map(m =>
                    m.id === lastMsg.id
                      ? { ...m, content: event.content || '' }
                      : m
                  );
                }
                return [
                  ...prev,
                  {
                    id: `stream-${Date.now()}`,
                    type: 'text' as MessageType,
                    content: event.content || '',
                    sender: 'ai' as const,
                    timestamp: nowTimestamp(),
                  },
                ];
              });
            } else if (event.content) {
              // Already have token content, use done content as final version
              finalContent = event.content;
            }
          }
        },
        () => {
          for (const step of steps) {
            if (step.status === 'loading') step.status = 'completed';
          }

          setMessages(prev => {
            const updated = prev.map(m =>
              m.id === toolMsgId
                ? { ...m, toolSteps: [...steps] }
                : m
            );
            // Append script summary card
            const scriptCard: Message = {
              id: `script-card-${Date.now()}`,
              type: 'script-card' as MessageType,
              sender: 'ai' as const,
              timestamp: new Date().toLocaleString('zh-CN', {
                year: 'numeric', month: '2-digit', day: '2-digit',
                hour: '2-digit', minute: '2-digit', second: '2-digit',
              }),
            };
            return [...updated, scriptCard];
          });
        },
        (error: string) => {
          setMessages(prev => [
            ...prev,
            {
              id: `error-${Date.now()}`,
              type: 'text' as MessageType,
              content: `生成出错：${error}`,
              sender: 'ai' as const,
              timestamp: nowTimestamp(),
            },
          ]);
        },
      );
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          type: 'text' as MessageType,
          content: `请求失败：${err instanceof Error ? err.message : String(err)}`,
          sender: 'ai' as const,
          timestamp: nowTimestamp(),
        },
      ]);
    }
  };

  // ── 倒计时：每秒 -1，到 0 自动提交 ──
  useEffect(() => {
    const activeMsgIds = Object.keys(countdowns).filter(
      id => countdowns[id] > 0 && !submittedForms.has(id)
    );
    if (activeMsgIds.length === 0) return;

    const timer = setInterval(() => {
      setCountdowns(prev => {
        const next = { ...prev };
        for (const id of activeMsgIds) {
          if (next[id] > 0 && !submittedForms.has(id)) {
            next[id] = next[id] - 1;
          }
        }
        return next;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [countdowns, submittedForms]);

  // 倒计时到 0 时自动提交
  useEffect(() => {
    for (const [msgId, remaining] of Object.entries(countdowns)) {
      if (remaining === 0 && !submittedForms.has(msgId)) {
        const msg = messages.find(m => m.id === msgId);
        if (msg?.configData) {
          handleConfigSubmit(msgId, msg.configData);
        }
      }
    }
  }, [countdowns, submittedForms, messages]);

  const handleStartCreation = async () => {
    if (!inputText.trim() || isLoading) return;

    const userInput = inputText.trim();
    setCurrentUserInput(userInput);
    setIsChatMode(true);
    setIsLoading(true);

    const userMsg: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: userInput,
      sender: 'user',
      timestamp: nowTimestamp(),
    };

    setMessages([userMsg]);
    setInputText('');
    setSelectedFiles([]);
    setFileError('');

    try {
      const chatResponse: ChatResponse = await sendChat(userInput, currentThreadId || undefined);

      if (chatResponse.type === 'config_form') {
        const { data } = chatResponse;
        setCurrentThreadId(data.thread_id);

        // Build defaults map
        const defaults: Record<string, string> = {};
        for (const field of data.fields) {
          defaults[field.id] = field.default;
        }

        const configMsg: Message = {
          id: (Date.now() + 1).toString(),
          type: 'config-form',
          sender: 'ai',
          timestamp: nowTimestamp(),
          configData: {
            threadId: data.thread_id,
            title: data.title,
            sections: data.fields.map(f => ({
              id: f.id,
              label: f.label,
              options: f.options.map(o => ({ label: o.label, value: o.value })),
            })),
            defaults,
          },
        };
        setMessages(prev => [...prev, configMsg]);
        setCountdowns(prev => ({ ...prev, [configMsg.id]: 60 }));
        void loadThreads();
      }
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          type: 'text' as MessageType,
          content: `请求失败：${err instanceof Error ? err.message : String(err)}`,
          sender: 'ai' as const,
          timestamp: nowTimestamp(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleChatSend = async () => {
    if (!inputText.trim() || isLoading) return;

    const userInput = inputText.trim();
    setCurrentUserInput(userInput);
    setIsLoading(true);

    const userMsg: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: userInput,
      sender: 'user',
      timestamp: nowTimestamp(),
    };
    setMessages(prev => [...prev, userMsg]);
    setInputText('');
    setSelectedFiles([]);
    setFileError('');

    try {
      const chatResponse: ChatResponse = await sendChat(userInput, currentThreadId || undefined);

      if (chatResponse.type === 'config_form') {
        const { data } = chatResponse;
        setCurrentThreadId(data.thread_id);

        const defaults: Record<string, string> = {};
        for (const field of data.fields) {
          defaults[field.id] = field.default;
        }

        const configMsg: Message = {
          id: (Date.now() + 1).toString(),
          type: 'config-form',
          sender: 'ai',
          timestamp: nowTimestamp(),
          configData: {
            threadId: data.thread_id,
            title: data.title,
            sections: data.fields.map(f => ({
              id: f.id,
              label: f.label,
              options: f.options.map(o => ({ label: o.label, value: o.value })),
            })),
            defaults,
          },
        };
        setMessages(prev => [...prev, configMsg]);
        setCountdowns(prev => ({ ...prev, [configMsg.id]: 60 }));
        void loadThreads();
      }
    } catch (err) {
      setMessages(prev => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          type: 'text' as MessageType,
          content: `请求失败：${err instanceof Error ? err.message : String(err)}`,
          sender: 'ai' as const,
          timestamp: nowTimestamp(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const removeSelectedFile = (fileToRemove: File) => {
    const keyToRemove = getFileKey(fileToRemove);
    setSelectedFiles(prev => prev.filter(file => getFileKey(file) !== keyToRemove));
  };

  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const incoming: File[] = event.target.files ? Array.from(event.target.files) : [];
    if (!incoming.length) return;

    const supported = incoming.filter(isSupportedUploadFile);
    const rejectedCount = incoming.length - supported.length;

    setSelectedFiles(prev => {
      const existing = new Set(prev.map(getFileKey));
      const appended = supported.filter(file => !existing.has(getFileKey(file)));
      return [...prev, ...appended];
    });

    if (rejectedCount > 0) {
      setFileError(`已忽略 ${rejectedCount} 个不支持的文件，仅支持图片和文档。`);
    } else {
      setFileError('');
    }

    // Reset input so the same file can be selected again.
    event.target.value = '';
  };

  const updateMessageCard = (
    msgId: string,
    updater: (card: NonNullable<Message['cardData']>) => NonNullable<Message['cardData']>,
  ) => {
    setMessages(prev =>
      prev.map(msg => {
        if (msg.id !== msgId || !msg.cardData) return msg;
        return { ...msg, cardData: updater(msg.cardData) };
      })
    );
  };

  const pollAsyncTask = async (
    taskId: string,
    onProgress: (task: AsyncTaskStatusResponse) => void,
    options?: {
      timeoutMs?: number;
      timeoutMessage?: string;
      isCancelled?: () => boolean;
      cancelMessage?: string;
    },
  ): Promise<AsyncTaskStatusResponse> => {
    const intervalMs = 2000;
    const timeoutMs = options?.timeoutMs ?? (20 * 60 * 1000);
    const startTs = Date.now();
    const terminalStatuses = new Set(['completed', 'failed', 'cancelled', 'obsolete', 'expired']);

    while (Date.now() - startTs < timeoutMs) {
      if (options?.isCancelled?.()) {
        throw new Error(options.cancelMessage || VIDEO_GENERATION_CANCEL_MESSAGE);
      }
      const task = await getStoryboardTaskStatus(taskId);
      if (options?.isCancelled?.()) {
        throw new Error(options.cancelMessage || VIDEO_GENERATION_CANCEL_MESSAGE);
      }
      onProgress(task);
      if (terminalStatuses.has(task.status)) {
        return task;
      }
      await new Promise(resolve => setTimeout(resolve, intervalMs));
    }

    throw new Error(options?.timeoutMessage || '任务轮询超时（20分钟）');
  };

  const handleGenerateStoryboard = async () => {
    if (!scriptData || isStoryboardGenerating) return;

    const cardMsgId = `storyboard-task-${Date.now()}`;
    const loadingCard: Message = {
      id: cardMsgId,
      type: 'storyboard-card',
      sender: 'ai',
      timestamp: nowTimestamp(),
      cardData: {
        title: '视频分镜',
        description: scriptData.synopsis || '正在基于剧本自动构建分镜结构',
        duration: formatScriptDuration(scriptData),
        style: scriptData.style || '2D卡通',
        state: 'loading',
        progress: 0,
        taskMessage: '正在填充视觉素材...',
        videoState: 'idle',
        videoProgress: 0,
        videoTaskMessage: '',
        videoError: '',
        videoSummary: '',
        mergedVideoUrl: '',
        actions: [],
        icon: <Clapperboard size={18} />,
      },
    };
    setMessages(prev => [...prev, loadingCard]);
    setIsStoryboardGenerating(true);

    try {
      const threadId = currentThreadId || `frontend-${Date.now()}`;
      const episode = await createEpisodeFromScript(
        scriptData,
        threadId,
        scriptData.title || currentUserInput || '未命名剧集'
      );
      setStoryboardEditorEpisodeId(episode.episode_id);
      const task = await generateStoryboards(episode.episode_id);
      if (currentThreadId || threadId) {
        void updateThreadState(currentThreadId || threadId, {
          current_episode_id: episode.episode_id,
          latest_task_id: task.task_id,
          latest_task_type: 'storyboard_generation',
          current_script_data_json: (scriptData as unknown as Record<string, unknown>) || {},
        }).catch(() => undefined);
      }

      updateMessageCard(cardMsgId, card => ({
        ...card,
        taskId: task.task_id,
        episodeId: episode.episode_id,
        progress: 5,
        taskMessage: task.message || '分镜任务已启动，正在填充视觉素材...',
      }));

      const finalTask = await pollAsyncTask(task.task_id, (status) => {
        updateMessageCard(cardMsgId, card => ({
          ...card,
          progress: status.progress,
          taskMessage: status.message || '正在填充视觉素材...',
          error: status.error || '',
        }));
      }, {
        timeoutMs: 20 * 60 * 1000,
        timeoutMessage: '分镜生成轮询超时（20分钟）',
      });

      if (finalTask.status !== 'completed') {
        throw new Error(finalTask.error || finalTask.message || '分镜生成失败');
      }

      updateMessageCard(cardMsgId, card => ({
        ...card,
        state: 'completed',
        progress: 100,
        taskMessage: '视觉素材填充完成',
        description: scriptData.synopsis || card.description,
        videoState: 'idle',
        videoProgress: 0,
        videoTaskMessage: '',
        videoError: '',
        videoSummary: '',
        mergedVideoUrl: '',
        actions: [
          { label: '生成视频', primary: true },
          { label: '手动编辑分镜' },
        ],
        stats: [
          { label: '角色', value: `${scriptData.characters.length} 角色`, icon: <Users size={16} /> },
          { label: '场景', value: `${scriptData.scenes.length} 场景`, icon: <MapPin size={16} /> },
          { label: '分镜', value: `${scriptData.shots.length} 分镜`, icon: <LayoutGrid size={16} /> },
          { label: '道具', value: `${scriptData.props.length} 道具`, icon: <Package size={16} /> },
        ],
      }));
    } catch (err) {
      updateMessageCard(cardMsgId, card => ({
        ...card,
        state: 'failed',
        taskMessage: '',
        error: err instanceof Error ? err.message : String(err),
        actions: [{ label: '重试生成分镜', primary: true }],
      }));
    } finally {
      setIsStoryboardGenerating(false);
    }
  };

  const setStoryboardVideoActionState = (storyboardMsgId: string | undefined, generating: boolean) => {
    if (!storyboardMsgId) return;
    updateMessageCard(storyboardMsgId, (card) => ({
      ...card,
      actions: generating
        ? [{ label: '手动编辑分镜' }]
        : [
            { label: '生成视频', primary: true },
            { label: '手动编辑分镜' },
          ],
    }));
  };

  const handleGenerateVideo = async (msgId: string) => {
    if (isVideoGenerating) return;

    const triggerMsg = messages.find(msg => msg.id === msgId);
    const episodeId = triggerMsg?.cardData?.episodeId;
    if (!episodeId) {
      updateMessageCard(msgId, card => ({
        ...card,
        videoState: 'failed',
        videoError: '未找到可用的剧集 ID，请先重新生成分镜',
        actions: [{ label: '重试生成分镜', primary: true }],
      }));
      return;
    }

    const isRetryInProgressCard = triggerMsg?.type === 'video-progress-card';
    const sourceStoryboardMsgId = triggerMsg?.type === 'storyboard-card'
      ? triggerMsg.id
      : triggerMsg?.cardData?.sourceStoryboardMsgId;
    const progressMsgId = isRetryInProgressCard
      ? msgId
      : `video-task-${episodeId}-${Date.now()}`;

    canceledVideoProgressCardIdsRef.current.delete(progressMsgId);
    if (isRetryInProgressCard) {
      updateMessageCard(progressMsgId, card => ({
        ...card,
        title: '视频生成任务',
        description: '系统正在排队并渲染分镜视频',
        episodeId,
        sourceStoryboardMsgId: sourceStoryboardMsgId || card.sourceStoryboardMsgId,
        videoState: 'loading',
        videoProgress: 0,
        videoTaskId: '',
        videoTaskMessage: '正在提交视频生成任务...',
        videoError: '',
        videoSummary: '',
        mergedVideoUrl: '',
        actions: [
          { label: '取消生成' },
          { label: '手动编辑分镜' },
        ],
        icon: <Clapperboard size={18} />,
      }));
    } else {
      const progressCard: Message = {
        id: progressMsgId,
        type: 'video-progress-card',
        sender: 'ai',
        timestamp: nowTimestamp(),
        cardData: {
          title: '视频生成任务',
          description: '系统正在排队并渲染分镜视频',
          episodeId,
          sourceStoryboardMsgId,
          duration: triggerMsg?.cardData?.duration || '--',
          style: triggerMsg?.cardData?.style || '2D卡通',
          videoState: 'loading',
          videoProgress: 0,
          videoTaskId: '',
          videoTaskMessage: '正在提交视频生成任务...',
          videoError: '',
          videoSummary: '',
          mergedVideoUrl: '',
          actions: [
            { label: '取消生成' },
            { label: '手动编辑分镜' },
          ],
          icon: <Clapperboard size={18} />,
        },
      };
      setMessages(prev => [...prev, progressCard]);
    }

    setStoryboardVideoActionState(sourceStoryboardMsgId, true);
    setIsVideoGenerating(true);
    const isCancelled = () => canceledVideoProgressCardIdsRef.current.has(progressMsgId);

    try {
      const task = await generateAigc(episodeId);
      if (currentThreadId) {
        void updateThreadState(currentThreadId, {
          latest_task_id: task.task_id,
          latest_task_type: 'aigc_generation',
          current_episode_id: episodeId,
        }).catch(() => undefined);
      }
      if (isCancelled()) {
        throw new Error(VIDEO_GENERATION_CANCEL_MESSAGE);
      }

      updateMessageCard(progressMsgId, card => ({
        ...card,
        videoTaskId: task.task_id,
        videoProgress: 5,
        videoTaskMessage: task.message || '正在生成视频，请稍候',
      }));

      const finalTask = await pollAsyncTask(task.task_id, (status) => {
        updateMessageCard(progressMsgId, card => ({
          ...card,
          videoProgress: status.progress,
          videoTaskMessage: status.message || '正在生成视频，请稍候',
          videoError: status.error || '',
        }));
      }, {
        timeoutMs: 120 * 60 * 1000,
        timeoutMessage: '视频生成轮询超时（120分钟）',
        isCancelled,
        cancelMessage: VIDEO_GENERATION_CANCEL_MESSAGE,
      });

      if (finalTask.status === 'cancelled') {
        throw new Error(VIDEO_GENERATION_CANCEL_MESSAGE);
      }
      if (finalTask.status !== 'completed') {
        throw new Error(finalTask.error || finalTask.message || '生成视频失败');
      }

      const media = await getEpisodeStoryboardMedia(episodeId);
      const sortedItems = [...media.items].sort((a, b) => a.storyboard_number - b.storyboard_number);
      const mergeClips = sortedItems
        .filter(item => Boolean(item.video_key || item.video_url))
        .map(item => ({
          video_url: item.video_key || item.video_url,
          duration: item.duration || 0,
          start_time: 0,
          end_time: 0,
          transition: { type: 'none', duration: 0 },
        }));

      if (mergeClips.length === 0) {
        throw new Error('未找到可合并的视频分镜');
      }

      if (isCancelled()) {
        throw new Error(VIDEO_GENERATION_CANCEL_MESSAGE);
      }

      updateMessageCard(progressMsgId, card => ({
        ...card,
        videoProgress: 0,
        videoTaskMessage: '分镜视频已生成，正在合并成片...',
        videoSummary: `已生成 ${mergeClips.length} 条分镜视频，开始合并`,
      }));

      const mergeOutput = `outputs/merged_episode_${episodeId}_${Date.now()}.mp4`;
      const mergeTask = await mergeEpisodeVideos(mergeClips, mergeOutput);

      updateMessageCard(progressMsgId, card => ({
        ...card,
        videoTaskId: mergeTask.task_id,
        videoProgress: 5,
        videoTaskMessage: mergeTask.message || '正在执行视频合并...',
      }));

      const mergeFinalTask = await pollAsyncTask(mergeTask.task_id, (status) => {
        updateMessageCard(progressMsgId, card => ({
          ...card,
          videoProgress: status.progress,
          videoTaskMessage: status.message || '正在执行视频合并...',
          videoError: status.error || '',
        }));
      }, {
        timeoutMs: 30 * 60 * 1000,
        timeoutMessage: '视频合并轮询超时（30分钟）',
        isCancelled,
        cancelMessage: VIDEO_GENERATION_CANCEL_MESSAGE,
      });

      if (mergeFinalTask.status === 'cancelled') {
        throw new Error(VIDEO_GENERATION_CANCEL_MESSAGE);
      }
      if (mergeFinalTask.status !== 'completed') {
        throw new Error(mergeFinalTask.error || mergeFinalTask.message || '视频合并失败');
      }

      let mergedVideoUrl = '';
      let summary = `视频已合并完成，共 ${mergeClips.length} 条分镜`;
      try {
        const parsed = mergeFinalTask.result ? JSON.parse(mergeFinalTask.result) : null;
        if (parsed && typeof parsed === 'object') {
          mergedVideoUrl = String(parsed.playable_url || parsed.merged_url || '').trim();
          const duration = Number(parsed.output_duration || 0);
          if (duration > 0) summary = `视频已合并完成，时长约 ${duration.toFixed(1)} 秒`;
        }
      } catch {
        // ignore malformed task.result
      }

      if (!mergedVideoUrl) {
        mergedVideoUrl = `/api/v1/storyboard/videos/merge/file/${mergeTask.task_id}`;
      }

      updateMessageCard(progressMsgId, card => ({
        ...card,
        videoState: 'completed',
        videoProgress: 100,
        videoTaskMessage: '视频生成完成',
        videoSummary: summary,
        mergedVideoUrl,
        actions: [
          { label: '重新生成视频', primary: true },
          { label: '手动编辑分镜' },
        ],
      }));
    } catch (err) {
      const rawError = err instanceof Error ? err.message : String(err);
      const displayError = rawError === VIDEO_GENERATION_CANCEL_MESSAGE
        ? '已取消本次生成（后台任务可能仍在执行）'
        : rawError;

      updateMessageCard(progressMsgId, card => ({
        ...card,
        videoState: 'failed',
        videoTaskMessage: '',
        videoError: displayError,
        actions: [
          { label: '重试生成视频', primary: true },
          { label: '手动编辑分镜' },
        ],
      }));
    } finally {
      canceledVideoProgressCardIdsRef.current.delete(progressMsgId);
      setStoryboardVideoActionState(sourceStoryboardMsgId, false);
      setIsVideoGenerating(false);
    }
  };

  const handleCancelVideoGeneration = async (msg: Message) => {
    const progressMsgId = msg.id;
    const sourceStoryboardMsgId = msg.cardData?.sourceStoryboardMsgId;
    const taskId = (msg.cardData?.videoTaskId || '').trim();

    canceledVideoProgressCardIdsRef.current.add(progressMsgId);
    updateMessageCard(progressMsgId, (card) => ({
      ...card,
      videoTaskMessage: '正在取消...',
      actions: [{ label: '手动编辑分镜' }],
    }));

    if (!taskId) {
      updateMessageCard(progressMsgId, (card) => ({
        ...card,
        videoState: 'failed',
        videoTaskMessage: '',
        videoError: '已取消本次生成',
        actions: [
          { label: '重试生成视频', primary: true },
          { label: '手动编辑分镜' },
        ],
      }));
      return;
    }

    try {
      const result = await cancelStoryboardTask(taskId);
      updateMessageCard(progressMsgId, (card) => ({
        ...card,
        videoState: 'failed',
        videoTaskMessage: '',
        videoError: result.message || '已提交取消请求',
        actions: [
          { label: '重试生成视频', primary: true },
          { label: '手动编辑分镜' },
        ],
      }));
      setStoryboardVideoActionState(sourceStoryboardMsgId, false);
    } catch (error) {
      updateMessageCard(progressMsgId, (card) => ({
        ...card,
        videoState: 'failed',
        videoTaskMessage: '',
        videoError: error instanceof Error ? error.message : String(error),
        actions: [
          { label: '重试生成视频', primary: true },
          { label: '手动编辑分镜' },
        ],
      }));
    }
  };

  const handleCardAction = (msg: Message, actionLabel: string) => {
    if (actionLabel.includes('取消生成')) {
      void handleCancelVideoGeneration(msg);
      return;
    }

    if (actionLabel.includes('重试')) {
      if (actionLabel.includes('视频')) {
        handleGenerateVideo(msg.id);
      } else {
        handleGenerateStoryboard();
      }
      return;
    }

    if (actionLabel.includes('生成视频')) {
      handleGenerateVideo(msg.id);
      return;
    }

    if (actionLabel.includes('手动编辑分镜')) {
      openStoryboardEditor(msg.cardData?.episodeId);
      return;
    }

    if (actionLabel.includes('查看剧本')) {
      setIsScriptOpen(true);
    }
  };

  return (
    <div className="flex h-[100dvh] bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-100 overflow-hidden font-sans">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={FILE_INPUT_ACCEPT}
        className="hidden"
        onChange={handleFileInputChange}
      />
      {/* Sidebar */}
      <aside
        className={`${isSidebarCollapsed ? 'w-[88px]' : 'w-[280px]'} flex-shrink-0 border-r border-gray-100 dark:border-gray-900 bg-gray-50/50 dark:bg-gray-900/50 flex flex-col h-full transition-all duration-300 ${isScriptOpen ? 'hidden lg:flex' : 'flex'}`}
      >
        <div className="h-16 flex items-center justify-between px-4">
          <div className={`flex items-center gap-2 ${isSidebarCollapsed ? 'hidden' : ''}`}>
            <div className="w-8 h-8 bg-black dark:bg-white rounded-lg flex items-center justify-center text-white dark:text-black">
              <Sparkles size={20} />
            </div>
          </div>
          <button
            onClick={() => setIsSidebarCollapsed(prev => !prev)}
            className="p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-500 transition-colors"
            title={isSidebarCollapsed ? '展开侧栏' : '折叠侧栏'}
          >
            {isSidebarCollapsed ? <PanelLeftOpen size={20} /> : <PanelLeftClose size={20} />}
          </button>
        </div>

        <div className="px-4 py-2 space-y-2">
          <button
            onClick={() => {
              resetComposerState();
            }}
            className={`w-full flex items-center justify-center gap-2 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-900 dark:text-white font-medium py-3 px-4 rounded-xl transition-all shadow-sm border border-gray-200 dark:border-gray-700 ${isSidebarCollapsed ? 'px-2' : ''}`}
            title="新建"
          >
            <Plus size={20} />
            {!isSidebarCollapsed && '新建'}
          </button>
          <button
            className={`w-full flex items-center justify-center gap-2 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-900 dark:text-white font-medium py-3 px-4 rounded-xl transition-all ${isSidebarCollapsed ? 'px-2' : ''}`}
            title="资产库"
          >
            <Library size={20} />
            {!isSidebarCollapsed && '资产库'}
          </button>
        </div>

        <div className={`mt-6 flex-1 flex flex-col min-h-0 ${isSidebarCollapsed ? 'hidden' : ''}`}>
          <div className="px-6 flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">历史记录</span>
            <button className="text-xs text-gray-400 hover:text-primary transition-colors">全部</button>
          </div>
          <div className="flex-1 overflow-y-auto custom-scrollbar ios-scroll px-4 pb-4 space-y-1">
            {isThreadsLoading ? (
              <div className="px-2 py-3 text-sm text-gray-400">加载中...</div>
            ) : threadItems.length === 0 ? (
              <div className="px-2 py-3 text-sm text-gray-400">暂无历史会话</div>
            ) : (
              threadItems.map((thread) => (
                <button
                  key={thread.thread_id}
                  onClick={() => {
                    void getThread(thread.thread_id).then(openThreadDetail).catch(() => undefined);
                  }}
                  className={`w-full text-left px-3 py-3 rounded-xl transition-colors ${
                    currentThreadId === thread.thread_id
                      ? 'bg-white dark:bg-gray-800 shadow-sm border border-gray-200 dark:border-gray-700'
                      : 'hover:bg-white/80 dark:hover:bg-gray-800/80'
                  }`}
                >
                  <div className="text-sm font-medium text-gray-800 dark:text-gray-100 line-clamp-2">
                    {thread.summary || thread.title}
                  </div>
                  <div className="mt-1 text-xs text-gray-400">
                    {new Date(thread.updated_at).toLocaleString('zh-CN', {
                      month: '2-digit',
                      day: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        <div className={`p-4 border-t border-gray-100 dark:border-gray-900 ${isSidebarCollapsed ? 'hidden' : ''}`}>
          <div className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 cursor-pointer transition-colors">
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-purple-500 to-pink-500 flex items-center justify-center text-white text-xs font-bold">
              U
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">User Name</p>
              <p className="text-xs text-gray-500 truncate">user@example.com</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className={`flex-1 flex flex-col relative overflow-hidden bg-white dark:bg-gray-950 ios-scroll ${isScriptOpen ? 'min-w-[360px]' : ''}`}>
        {/* Top Bar */}
        <div className="h-16 flex items-center justify-end px-6 gap-4 z-10 border-b border-gray-50 dark:border-gray-900">
          <div className="flex items-center bg-purple-50 dark:bg-purple-900/20 px-3 py-1.5 rounded-full border border-purple-100 dark:border-purple-800">
            <Crown size={16} className="text-primary mr-1" />
            <span className="text-primary font-medium text-sm cursor-pointer hover:underline">订阅</span>
          </div>
          <button className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-900 text-gray-500 transition-colors">
            <HelpCircle size={20} />
          </button>
          <button className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-900 text-gray-500 transition-colors">
            <MessageSquare size={20} />
          </button>
        </div>

        <div ref={scrollContainerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto custom-scrollbar ios-scroll">
          <AnimatePresence mode="wait">
            {!isChatMode ? (
              <motion.div
                key="hero"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="h-full flex flex-col items-center justify-center w-full max-w-5xl mx-auto px-6 pb-20"
              >
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-center mb-12"
                >
                  <h1 className="text-4xl md:text-5xl font-semibold mb-4 tracking-tight">
                    你好，你的创作空间已就绪。
                  </h1>
                </motion.div>

                {/* Input Area (Hero) */}
                <div className="w-full max-w-4xl relative group">
                  <div className="absolute -inset-0.5 bg-gradient-to-r from-primary/30 to-blue-500/30 rounded-3xl blur opacity-75 group-hover:opacity-100 transition duration-500"></div>
                  <div className="relative w-full bg-white dark:bg-gray-900 rounded-[2rem] border border-primary/20 dark:border-primary/40 shadow-xl flex flex-col min-h-[220px]">
                    <textarea
                      value={inputText}
                      onChange={(e) => setInputText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleStartCreation();
                        }
                      }}
                      className="w-full flex-1 bg-transparent border-0 rounded-[2rem] p-8 text-lg md:text-xl text-gray-800 dark:text-gray-100 placeholder-gray-300 dark:placeholder-gray-600 focus:ring-0 resize-none outline-none"
                      placeholder="告诉我，你今天想创造一点什么？"
                    />
                    <div className="px-6 pb-6 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <button
                          onClick={openFilePicker}
                          className="w-10 h-10 rounded-full bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center justify-center text-gray-500 transition-colors"
                          title="上传图片或文档"
                        >
                          <Plus size={20} />
                        </button>
                      </div>
                      <button
                        onClick={handleStartCreation}
                        disabled={isLoading || !inputText.trim()}
                        className="bg-black dark:bg-white text-white dark:text-black hover:bg-gray-800 dark:hover:bg-gray-200 h-12 px-6 rounded-full flex items-center gap-2 font-medium transition-all shadow-lg hover:shadow-xl transform hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {isLoading ? (
                          <Loader2 size={18} className="animate-spin" />
                        ) : (
                          <Sparkles size={18} fill="currentColor" />
                        )}
                        <span>开始创作</span>
                        <ArrowRight size={18} />
                      </button>
                    </div>
                    {(selectedFiles.length > 0 || fileError) && (
                      <div className="px-6 pb-5">
                        {selectedFiles.length > 0 && (
                          <div className="flex flex-wrap gap-2 mb-2">
                            {selectedFiles.map((file) => (
                              <div
                                key={getFileKey(file)}
                                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-100 dark:bg-gray-800 text-xs text-gray-700 dark:text-gray-200"
                              >
                                {isImageFile(file) ? <ImageIcon size={12} /> : <FileText size={12} />}
                                <span className="max-w-[180px] truncate">{file.name}</span>
                                <button
                                  onClick={() => removeSelectedFile(file)}
                                  className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                                  aria-label={`移除文件 ${file.name}`}
                                  title="移除"
                                >
                                  <X size={12} />
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                        {fileError && (
                          <p className="text-xs text-orange-500">{fileError}</p>
                        )}
                      </div>
                    )}
                  </div>
                </div>

              </motion.div>
            ) : (
              <motion.div
                key="chat"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="w-full max-w-4xl mx-auto px-6 py-10 space-y-8"
              >
                {messages.map((msg) => (
                  <div key={msg.id} className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                    {msg.type === 'user' && (
                      <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl px-4 py-2 max-w-[80%] text-sm">
                        {msg.content}
                      </div>
                    )}

                    {msg.type === 'tool-call' && (
                      <div className="w-full bg-gray-50/50 dark:bg-gray-900/50 border border-gray-100 dark:border-gray-800 rounded-2xl p-6">
                        <div className="flex items-center justify-between mb-4">
                          <div className="flex items-center gap-2 text-sm font-medium">
                            <Settings2 size={18} className="text-green-500" />
                            <span>工具调用</span>
                          </div>
                          <div className="flex items-center gap-2 text-xs text-gray-400">
                            <span>{msg.toolSteps?.filter(s => s.status === 'completed').length}/{msg.toolSteps?.length} 项</span>
                            <ChevronDown size={14} />
                          </div>
                        </div>
                        <div className="space-y-3">
                          {msg.toolSteps?.map((step, i) => (
                            <div key={i} className="flex items-center justify-between text-sm">
                              <div className="flex items-center gap-3">
                                <div className={`w-1.5 h-1.5 rounded-full ${step.status === 'loading' ? 'bg-blue-500 animate-pulse' : step.status === 'completed' ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'}`} />
                                <span className="font-medium">{step.label}</span>
                                {step.detail && <span className="text-gray-400">{step.detail}</span>}
                              </div>
                              {step.status === 'completed' && <CheckCircle2 size={16} className="text-green-500" />}
                              {step.status === 'loading' && <Loader2 size={16} className="text-blue-500 animate-spin" />}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {msg.type === 'config-form' && msg.configData && (
                      <div className="w-full bg-gray-50/50 dark:bg-gray-900/50 border border-gray-100 dark:border-gray-800 rounded-2xl p-6">
                        <div className="flex items-center justify-between mb-6">
                          <div className="flex items-center gap-2 font-medium">
                            <FileText size={18} />
                            <span>{msg.configData.title}</span>
                          </div>
                          <button 
                            onClick={() => toggleFormCollapse(msg.id)}
                            className="text-gray-400 hover:text-gray-600 transition-colors"
                          >
                            <ChevronDown 
                              size={18} 
                              className={`transition-transform ${collapsedForms.has(msg.id) ? '-rotate-90' : ''}`} 
                            />
                          </button>
                        </div>
                        {!collapsedForms.has(msg.id) && (
                        <div className="space-y-6">
                          {msg.configData.sections.map((section) => {
                            const selectedValue = getSelectedValue(msg.id, section.id, msg.configData!.defaults[section.id] || '');
                            return (
                              <div key={section.id} className="space-y-3">
                                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300">{section.label}</h4>
                                <div className="flex flex-wrap gap-2">
                                  {section.options.map((opt) => (
                                    <button
                                      key={opt.value}
                                      onClick={() => handleOptionSelect(msg.id, section.id, opt.value)}
                                      disabled={submittedForms.has(msg.id)}
                                      className={`px-4 py-1.5 rounded-full text-xs font-medium transition-all ${
                                        selectedValue === opt.value
                                          ? 'bg-purple-100 dark:bg-purple-900/30 text-primary border border-primary/30'
                                          : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
                                      } ${submittedForms.has(msg.id) ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}
                                    >
                                      {opt.label}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                        )}
                        <div className="mt-8 flex justify-end">
                          {submittedForms.has(msg.id) ? (
                            <button className="px-6 py-2 bg-gray-100 dark:bg-gray-800 text-gray-400 rounded-lg text-sm font-medium cursor-not-allowed" disabled>
                              已提交
                            </button>
                          ) : (
                            <button
                              onClick={() => handleConfigSubmit(msg.id, msg.configData!)}
                              className="px-6 py-2 bg-black dark:bg-white text-white dark:text-black rounded-lg text-sm font-medium hover:opacity-90 transition-all"
                            >
                              确认提交{countdowns[msg.id] != null && countdowns[msg.id] > 0 ? ` (${countdowns[msg.id]}s)` : ''}
                            </button>
                          )}
                        </div>
                      </div>
                    )}

                    {msg.type === 'text' && (
                      <div className="w-full bg-white dark:bg-gray-950 rounded-2xl px-1 py-2 max-w-[90%]">
                        <div className="text-sm leading-relaxed">{renderScriptContent(msg.content)}</div>
                      </div>
                    )}

                    {msg.type === 'script-card' && (
                      <div className="w-full bg-gray-50/50 dark:bg-gray-900/50 border border-gray-100 dark:border-gray-800 rounded-2xl overflow-hidden mt-4">
                        <div className="p-6">
                          {/* Header: 剧本 + 时长 */}
                          <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-2">
                              <FileText size={18} />
                              <span className="font-medium">剧本</span>
                            </div>
                            <div className="flex items-center gap-1.5 text-xs text-gray-400">
                              <Clock size={14} />
                              <span>{formatScriptDuration(scriptData)}</span>
                            </div>
                          </div>

                          {/* 故事标签 + 标题 + 风格 */}
                          <div className="flex items-center gap-2 mb-4">
                            <span className="bg-gray-200 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-2 py-0.5 rounded text-xs font-medium">
                              故事
                            </span>
                            <span className="text-sm text-gray-700 dark:text-gray-300 truncate">{scriptData?.title || currentUserInput || '剧本创作'}</span>
                            <div className="flex-1" />
                            <div className="flex items-center gap-1.5 bg-purple-100 dark:bg-purple-900/30 text-primary px-2 py-1 rounded-full text-xs font-medium">
                              <Palette size={14} />
                              <span>{scriptData?.style || '日漫 电影质感'}</span>
                            </div>
                          </div>

                          {/* 引导提示 */}
                          {!dismissedHints.has(msg.id) && (
                          <div className="bg-purple-50 dark:bg-purple-900/20 border border-purple-100 dark:border-purple-800/50 rounded-xl p-4 flex items-start gap-3 relative">
                            <div className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-sm">
                              <Lightbulb size={20} className="text-primary" />
                            </div>
                            <div className="flex-1">
                              <h4 className="text-sm font-semibold text-primary mb-1">开始创作您的视频</h4>
                              <p className="text-xs text-gray-500 dark:text-gray-400">
                                点击"生成分镜"开始下一步，您也可以继续对话完善您的视频分镜
                              </p>
                            </div>
                            <button
                              onClick={() => setDismissedHints(prev => new Set(prev).add(msg.id))}
                              className="text-gray-400 hover:text-gray-600"
                            >
                              <X size={16} />
                            </button>
                          </div>
                          )}
                        </div>

                        {/* Footer: 时间 + 操作按钮 */}
                        <div className="px-6 py-4 bg-gray-100/50 dark:bg-gray-800/50 flex items-center justify-between">
                          <span className="text-xs text-gray-400">{msg.timestamp}</span>
                          <div className="flex gap-2">
                            <button 
                              onClick={() => setIsScriptOpen(true)}
                              className="px-4 py-1.5 rounded-lg text-sm font-medium bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600 transition-all"
                            >
                              查看剧本
                            </button>
                            <button
                              onClick={handleGenerateStoryboard}
                              disabled={!scriptData || isStoryboardGenerating}
                              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                                !scriptData || isStoryboardGenerating
                                  ? 'bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-300 cursor-not-allowed'
                                  : 'bg-black dark:bg-white text-white dark:text-black hover:opacity-90'
                              }`}
                            >
                              {isStoryboardGenerating ? '分镜生成中...' : '生成分镜'}
                            </button>
                          </div>
                        </div>
                      </div>
                    )}

                    {msg.type === 'video-progress-card' && msg.cardData && (
                      <div className="w-full bg-gray-50/50 dark:bg-gray-900/50 border border-gray-100 dark:border-gray-800 rounded-2xl overflow-hidden mt-4">
                        <div className="p-6">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              {msg.cardData.videoState === 'loading' ? (
                                <Loader2 size={18} className="text-amber-500 animate-spin" />
                              ) : msg.cardData.videoState === 'completed' ? (
                                <CheckCircle2 size={18} className="text-emerald-500" />
                              ) : (
                                <Clapperboard size={18} className="text-slate-500" />
                              )}
                              <span className="font-medium">{msg.cardData.title || '视频生成任务'}</span>
                            </div>
                            <div className="text-xs text-gray-400">
                              {msg.cardData.videoProgress || 0}%
                            </div>
                          </div>

                          <div className="mt-4 rounded-xl border border-amber-100/80 dark:border-amber-800/40 overflow-hidden">
                            <div className="h-24 bg-gradient-to-r from-slate-200 via-slate-100 to-slate-200 dark:from-slate-800 dark:via-slate-700 dark:to-slate-800 relative">
                              <div className="absolute inset-0 bg-white/30 dark:bg-black/20 backdrop-blur-[1px]" />
                              <div className="absolute inset-0 flex items-center justify-center">
                                {msg.cardData.videoState === 'loading' ? (
                                  <Loader2 size={22} className="text-slate-600 dark:text-slate-300 animate-spin" />
                                ) : msg.cardData.videoState === 'completed' ? (
                                  <CheckCircle2 size={22} className="text-emerald-500" />
                                ) : (
                                  <Clapperboard size={22} className="text-slate-500 dark:text-slate-300" />
                                )}
                              </div>
                            </div>
                            <div className="p-4 bg-white dark:bg-gray-900/60">
                              <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                                {msg.cardData.videoState === 'loading'
                                  ? '正在生成视频...'
                                  : msg.cardData.videoState === 'completed'
                                    ? '视频生成完成'
                                    : msg.cardData.videoState === 'failed'
                                      ? '视频生成失败'
                                      : '视频任务待开始'}
                              </p>
                              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                {msg.cardData.videoTaskMessage || '系统正在排队处理中'}
                              </p>
                              <div className="mt-3 h-1.5 w-full bg-amber-100 dark:bg-amber-900/40 rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-amber-500 transition-all duration-500"
                                  style={{ width: `${Math.max(0, Math.min(100, msg.cardData.videoProgress || 0))}%` }}
                                />
                              </div>
                            </div>
                          </div>

                          {msg.cardData.videoState === 'completed' && (
                            <div className="mt-4 p-4 bg-emerald-50/70 dark:bg-emerald-900/10 rounded-xl border border-emerald-100 dark:border-emerald-800/40">
                              <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">视频生成完成</p>
                              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                {msg.cardData.videoSummary || '可继续下一步合成或编辑'}
                              </p>
                              {msg.cardData.mergedVideoUrl ? (
                                <div className="mt-4 bg-white dark:bg-gray-900/70 border border-emerald-100 dark:border-emerald-900/40 rounded-lg p-3">
                                  <video
                                    controls
                                    preload="metadata"
                                    playsInline
                                    className="w-full rounded-md bg-black"
                                    src={msg.cardData.mergedVideoUrl}
                                  />
                                </div>
                              ) : (
                                <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
                                  当前没有可播放的合并视频地址，请稍后重试。
                                </p>
                              )}
                            </div>
                          )}

                          {msg.cardData.videoState === 'failed' && (
                            <div className="mt-4 p-4 bg-rose-50/70 dark:bg-rose-900/10 rounded-xl border border-rose-200 dark:border-rose-800/40">
                              <p className="text-sm font-semibold text-rose-600 dark:text-rose-400">视频生成失败</p>
                              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{msg.cardData.videoError || '请重试'}</p>
                            </div>
                          )}
                        </div>

                        <div className="px-6 py-4 bg-gray-100/50 dark:bg-gray-800/50 flex items-center justify-between">
                          <span className="text-xs text-gray-400">{msg.timestamp}</span>
                          <div className="flex gap-2">
                            {msg.cardData.actions.map((action, i) => (
                              <button
                                key={i}
                                onClick={() => handleCardAction(msg, action.label)}
                                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                                  action.primary
                                    ? 'bg-black dark:bg-white text-white dark:text-black hover:opacity-90'
                                    : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                                }`}
                              >
                                {action.label}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}

                    {(msg.type === 'action-card' || msg.type === 'storyboard-card') && msg.cardData && (
                      <div className="w-full bg-gray-50/50 dark:bg-gray-900/50 border border-gray-100 dark:border-gray-800 rounded-2xl overflow-hidden mt-4">
                        <div className="p-6">
                          <div className="flex items-center justify-between mb-4">
                            <div className="flex items-center gap-2">
                              {msg.type === 'storyboard-card' && msg.cardData.state === 'loading' ? (
                                <Loader2 size={18} className="text-blue-500 animate-spin" />
                              ) : (
                                msg.cardData.icon
                              )}
                              <span className="font-medium">{msg.cardData.title}</span>
                            </div>
                            <div className="flex items-center gap-2 text-xs text-gray-400">
                              <Clock size={14} />
                              <span>{msg.type === 'storyboard-card' ? formatScriptDuration(scriptData) : msg.cardData.duration}</span>
                            </div>
                          </div>

                          <div className="flex items-center gap-2 mb-4">
                            <span className="bg-gray-200 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-2 py-0.5 rounded text-xs font-medium">
                              故事
                            </span>
                            {msg.type === 'action-card' && <span className="text-sm text-gray-500">{msg.cardData.description}</span>}
                            <div className="flex-1" />
                            <div className="flex items-center gap-1.5 bg-purple-100 dark:bg-purple-900/30 text-primary px-2 py-1 rounded-full text-xs font-medium">
                              <Palette size={14} />
                              <span>{msg.cardData.style || '2D卡通'}</span>
                            </div>
                          </div>

                          {msg.type === 'storyboard-card' && msg.cardData.state === 'loading' && (
                            <div className="mb-6 p-4 bg-blue-50/60 dark:bg-blue-900/10 rounded-xl border border-blue-100 dark:border-blue-800/40">
                              <div className="flex items-start gap-3">
                                <Loader2 size={18} className="mt-0.5 text-blue-500 animate-spin" />
                                <div className="flex-1">
                                  <p className="text-sm font-semibold text-blue-600 dark:text-blue-400">正在填充视觉素材...</p>
                                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                    {msg.cardData.taskMessage || '正在生成分镜结构，请稍候'}
                                  </p>
                                  <div className="mt-3 h-1.5 w-full bg-blue-100 dark:bg-blue-900/40 rounded-full overflow-hidden">
                                    <div
                                      className="h-full bg-blue-500 transition-all duration-500"
                                      style={{ width: `${Math.max(0, Math.min(100, msg.cardData.progress || 0))}%` }}
                                    />
                                  </div>
                                </div>
                                <span className="text-xs text-blue-500">{msg.cardData.progress || 0}%</span>
                              </div>
                            </div>
                          )}

                          {msg.type === 'storyboard-card' && msg.cardData.state === 'failed' && (
                            <div className="mb-6 p-4 bg-rose-50/70 dark:bg-rose-900/10 rounded-xl border border-rose-200 dark:border-rose-800/40">
                              <p className="text-sm font-semibold text-rose-600 dark:text-rose-400">分镜生成失败</p>
                              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{msg.cardData.error || '请重试'}</p>
                            </div>
                          )}

                          {msg.type === 'storyboard-card' && msg.cardData.state !== 'loading' && msg.cardData.state !== 'failed' && (
                            <div className="mb-6 p-4 bg-white dark:bg-gray-800/50 rounded-xl border border-gray-100 dark:border-gray-800">
                              <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-3 mb-4 leading-relaxed">
                                {msg.cardData.description}
                              </p>
                              <div className="flex flex-wrap gap-4">
                                {msg.cardData.stats?.map((stat, i) => (
                                  <div key={i} className="flex items-center gap-1.5 text-xs text-gray-500">
                                    {stat.icon}
                                    <span>{stat.value}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {msg.type === 'storyboard-card' && msg.cardData.videoState === 'loading' && (
                            <div className="mb-6 p-4 bg-amber-50/70 dark:bg-amber-900/10 rounded-xl border border-amber-100 dark:border-amber-800/40">
                              <div className="flex items-start gap-3">
                                <Loader2 size={18} className="mt-0.5 text-amber-500 animate-spin" />
                                <div className="flex-1">
                                  <p className="text-sm font-semibold text-amber-600 dark:text-amber-400">正在处理视频...</p>
                                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                    {msg.cardData.videoTaskMessage || '正在调用模型生成视频'}
                                  </p>
                                  <div className="mt-3 h-1.5 w-full bg-amber-100 dark:bg-amber-900/40 rounded-full overflow-hidden">
                                    <div
                                      className="h-full bg-amber-500 transition-all duration-500"
                                      style={{ width: `${Math.max(0, Math.min(100, msg.cardData.videoProgress || 0))}%` }}
                                    />
                                  </div>
                                </div>
                                <span className="text-xs text-amber-600">{msg.cardData.videoProgress || 0}%</span>
                              </div>
                            </div>
                          )}

                          {msg.type === 'storyboard-card' && msg.cardData.videoState === 'completed' && (
                            <div className="mb-6 p-4 bg-emerald-50/70 dark:bg-emerald-900/10 rounded-xl border border-emerald-100 dark:border-emerald-800/40">
                              <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">视频生成完成</p>
                              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                                {msg.cardData.videoSummary || '可继续下一步合成或编辑'}
                              </p>
                              {msg.cardData.mergedVideoUrl ? (
                                <div className="mt-4 bg-white dark:bg-gray-900/70 border border-emerald-100 dark:border-emerald-900/40 rounded-lg p-3">
                                  <video
                                    controls
                                    preload="metadata"
                                    playsInline
                                    className="w-full rounded-md bg-black"
                                    src={msg.cardData.mergedVideoUrl}
                                  />
                                </div>
                              ) : (
                                <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
                                  当前没有可播放的合并视频地址，请稍后重试。
                                </p>
                              )}
                            </div>
                          )}

                          {msg.type === 'storyboard-card' && msg.cardData.videoState === 'failed' && (
                            <div className="mb-6 p-4 bg-rose-50/70 dark:bg-rose-900/10 rounded-xl border border-rose-200 dark:border-rose-800/40">
                              <p className="text-sm font-semibold text-rose-600 dark:text-rose-400">视频生成失败</p>
                              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{msg.cardData.videoError || '请重试'}</p>
                            </div>
                          )}

                          {!dismissedHints.has(msg.id) && (
                          <div className="bg-purple-50 dark:bg-purple-900/20 border border-purple-100 dark:border-purple-800/50 rounded-xl p-4 flex items-start gap-3 relative">
                            <div className="p-2 bg-white dark:bg-gray-800 rounded-lg shadow-sm">
                              {msg.type === 'storyboard-card' && (msg.cardData.state === 'loading' || msg.cardData.videoState === 'loading') ? (
                                <Loader2 size={20} className="text-primary animate-spin" />
                              ) : (
                                <Lightbulb size={20} className="text-primary" />
                              )}
                            </div>
                            <div className="flex-1">
                              <h4 className="text-sm font-semibold text-primary mb-1">
                                {msg.type === 'storyboard-card'
                                  ? msg.cardData.state === 'loading'
                                    ? '正在生成分镜'
                                    : msg.cardData.videoState === 'loading'
                                      ? '正在生成视频'
                                      : msg.cardData.videoState === 'completed'
                                        ? '视频生成已完成'
                                        : '完成您的视频创作'
                                  : '开始创作您的视频'}
                              </h4>
                              <p className="text-xs text-gray-500 dark:text-gray-400">
                                {msg.type === 'storyboard-card'
                                  ? msg.cardData.state === 'loading'
                                    ? '系统正在分析镜头并填充视觉素材，完成后将自动切换到分镜卡片'
                                    : msg.cardData.videoState === 'loading'
                                      ? '系统正在逐条分镜生成图片与视频素材，请耐心等待'
                                      : msg.cardData.videoState === 'completed'
                                        ? '分镜对应的视频素材已生成，可继续编辑或进入下一步合成'
                                        : '您可以点击"生成视频"直接生成，或点击"手动编辑分镜"编辑后生成视频'
                                  : '点击"生成分镜"开始下一步，您也可以继续对话完善您的视频分镜'}
                              </p>
                            </div>
                            <button
                              onClick={() => setDismissedHints(prev => new Set(prev).add(msg.id))}
                              className="text-gray-400 hover:text-gray-600"
                            >
                              <X size={16} />
                            </button>
                          </div>
                          )}
                        </div>
                        <div className="px-6 py-4 bg-gray-100/50 dark:bg-gray-800/50 flex items-center justify-between">
                          <span className="text-xs text-gray-400">{msg.timestamp}</span>
                          <div className="flex gap-2">
                            {msg.type === 'storyboard-card' && msg.cardData.state === 'loading' && (
                              <button
                                disabled
                                className="px-4 py-1.5 rounded-lg text-sm font-medium bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-300 cursor-not-allowed"
                              >
                                分镜生成中...
                              </button>
                            )}
                            {msg.type === 'storyboard-card' && msg.cardData.videoState === 'loading' && (
                              <button
                                disabled
                                className="px-4 py-1.5 rounded-lg text-sm font-medium bg-gray-300 dark:bg-gray-700 text-gray-500 dark:text-gray-300 cursor-not-allowed"
                              >
                                视频生成中...
                              </button>
                            )}
                            {msg.cardData.actions.map((action, i) => (
                              <button
                                key={i}
                                onClick={() => handleCardAction(msg, action.label)}
                                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all ${
                                  action.primary
                                    ? 'bg-black dark:bg-white text-white dark:text-black hover:opacity-90'
                                    : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                                }`}
                              >
                                {action.label}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Bottom Input Area (Chat Mode) */}
        <AnimatePresence>
          {isChatMode && (
            <motion.div
              initial={{ y: 100 }}
              animate={{ y: 0 }}
              className="p-6 border-t border-gray-50 dark:border-gray-900 bg-white dark:bg-gray-950"
            >
              <div className="max-w-4xl mx-auto">
                <div className="relative bg-gray-50 dark:bg-gray-900 border border-gray-100 dark:border-gray-800 rounded-2xl shadow-sm">
                  <textarea
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        handleChatSend();
                      }
                    }}
                    className="w-full bg-transparent border-0 rounded-2xl p-4 pr-20 text-sm text-gray-800 dark:text-gray-100 placeholder-gray-400 focus:ring-0 resize-none outline-none min-h-[60px]"
                    placeholder="与综合助手对话，支持多种能力..."
                  />
                  {selectedFiles.length > 0 && (
                    <div className="px-4 pt-2 flex flex-wrap gap-2">
                      {selectedFiles.map((file) => (
                        <div
                          key={getFileKey(file)}
                          className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-gray-100 dark:bg-gray-800 text-[11px] text-gray-700 dark:text-gray-200"
                        >
                          {isImageFile(file) ? <ImageIcon size={11} /> : <FileText size={11} />}
                          <span className="max-w-[150px] truncate">{file.name}</span>
                          <button
                            onClick={() => removeSelectedFile(file)}
                            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                            aria-label={`移除文件 ${file.name}`}
                            title="移除"
                          >
                            <X size={11} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="px-4 pb-3 flex items-center justify-between">
                    <button
                      onClick={openFilePicker}
                      className="p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-500 transition-colors"
                      title="上传图片或文档"
                    >
                      <Plus size={18} />
                    </button>
                    <button
                      disabled={!inputText.trim() || isLoading}
                      onClick={handleChatSend}
                      className={`w-8 h-8 rounded-full flex items-center justify-center transition-all ${
                        inputText.trim() && !isLoading
                          ? 'bg-black dark:bg-white text-white dark:text-black shadow-md'
                          : 'bg-gray-200 dark:bg-gray-800 text-gray-400'
                      }`}
                    >
                      {isLoading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
                    </button>
                  </div>
                </div>
                <p className="text-center text-[10px] text-gray-400 mt-4">
                  AI 可能会犯错，内容仅供参考，请核查重要信息。
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Collapse toggle on right edge — open script panel */}
        {!isScriptOpen && (
          <button
            onClick={() => setIsScriptOpen(true)}
            className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-1/2 z-10 w-7 h-14 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-full flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors shadow-md"
          >
            <ChevronLeft size={16} />
          </button>
        )}
      </main>

      {/* Script Detail Drawer */}
      <ScriptView
        isOpen={isScriptOpen}
        onClose={() => setIsScriptOpen(false)}
        scriptData={scriptData}
      />

      <AnimatePresence>
        {isStoryboardEditorOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[120] bg-black/45 backdrop-blur-[2px] p-2 md:p-4"
            onClick={() => setIsStoryboardEditorOpen(false)}
          >
            <motion.div
              initial={{ y: 18, opacity: 0.96 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 12, opacity: 0.96 }}
              className="w-full h-full bg-white dark:bg-slate-950 rounded-xl overflow-hidden shadow-2xl border border-slate-200/70 dark:border-slate-800"
              onClick={(event) => event.stopPropagation()}
            >
              <StoryEditorPage
                onClose={() => setIsStoryboardEditorOpen(false)}
                scriptData={scriptData}
                mediaItems={storyboardEditorMediaItems}
                characterImages={storyboardEditorCharacterImages}
                loadingMedia={isStoryboardEditorMediaLoading && !!storyboardEditorEpisodeId}
                onSave={handleSaveStoryboardEdits}
                initialState={storyEditorState}
                onStateChange={setStoryEditorState}
              />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
