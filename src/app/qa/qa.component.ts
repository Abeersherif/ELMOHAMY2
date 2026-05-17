import { Component, ChangeDetectorRef } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { environment } from '../../environments/environment';

interface ChatMessage {
  sender: 'user' | 'bot';
  text: string;
  articles?: Law[];
}

interface Law {
  id: number;
  law_name: string | null;
  main_category: string | null;
  number: string | null;
  titel: string | null;
  details: string | null;
  table?: string | null;
  is_cancelled?: boolean;
  cancellation_signal?: string;
}

interface UserOption {
  text: string;
  action: string;
}

interface AskResponse {
  intent?: string;
  confidence?: number;
  summary?: string | null;
  steps?: string[];
  answer?: string | null;
  articles?: Law[];
  total_articles?: number;
  verification?: {
    verified: boolean;
    relevance_score: number;
    message: string;
    filtered_articles?: Law[];
    cancelled_warning?: boolean;
    precedent_warning?: boolean;
    precedent_refs?: string[];
    law_existence_warning?: {
      user_cited: string;
      exists: boolean;
      suggestions: Array<{
        T_No: number;
        T_Year: number;
        law_name?: string;
        tash_name?: string;
        reason?: string;
      }>;
    } | null;
  };
  cancelled_count?: number;
  rulings_count?: number;
  stage?:
  | 'clarification'
  | 'final_answer'
  | 'no_results'
  | 'details'
  | 'error'
  | 'selection_details'
  | 'selection_error';
  needs_clarification?: boolean;
  clarification_question?: string | null;
  clarification_options?: string[];
  laws?: Law[];
  message?: string;
  user_options?: UserOption[];
  retrieval_log?: string[];
  chosen_categories?: string[];
  debug?: any;
}

interface ChatSession {
  session_id: string;
  title: string;
  last_at: string;
  turns: number;
}

@Component({
  selector: 'app-qa',
  standalone: true,
  templateUrl: './qa.component.html',
  styleUrls: ['./qa.component.css'],
  imports: [CommonModule, FormsModule],
})
export class QaComponent {
  apiUrl = `${environment.apiUrl}/ask`;
  uploadUrl = `${environment.apiUrl}/upload_document`;
  explainUrl = `${environment.apiUrl}/explain_article`;
  historyUrl = `${environment.apiUrl}/history`;
  sessionsUrl = `${environment.apiUrl}/sessions`;

  userInput = '';
  chatHistory: ChatMessage[] = [];
  clarificationOptions: string[] = [];
  isLoading = false;
  isUploading = false;

  showBrowseModal = false;
  lawCategories: any[] = [];
  isLoadingCategories = false;

  lastArticles: Law[] = [];

  sessions: ChatSession[] = [];
  sidebarOpen = false;
  pendingDeleteSession: ChatSession | null = null;

  needsConsent = false;
  consentAge = false;
  consentPrivacy = false;

  pendingUploadFile: File | null = null;
  uploadConsentDone = false;

  reportingIndex: number | null = null;
  reportText = '';
  reportUrl = `${environment.apiUrl}/report`;
  consentUrl = `${environment.apiUrl}/consent`;

  private currentRequest: Subscription | null = null;

  sessionId: string;
  ownerId: string;

  constructor(
    private http: HttpClient,
    private cdr: ChangeDetectorRef
  ) {
    const savedOwner = localStorage.getItem('mohamy_owner_id');
    if (savedOwner) {
      this.ownerId = savedOwner;
    } else {
      this.ownerId = this.generateSessionId();
      localStorage.setItem('mohamy_owner_id', this.ownerId);
    }

    const saved = localStorage.getItem('mohamy_session_id');
    if (saved && !saved.startsWith('web-')) {
      this.sessionId = saved;
    } else {
      this.sessionId = this.generateSessionId();
      localStorage.setItem('mohamy_session_id', this.sessionId);
    }
  }

  private generateSessionId(): string {
    const cryptoRef = (globalThis as any).crypto;
    if (cryptoRef?.randomUUID) {
      return cryptoRef.randomUUID();
    }
    // RFC4122 v4 fallback for very old browsers
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }

  ngOnInit(): void {
    this.needsConsent = !localStorage.getItem('mohamy_consent_v1');
    this.uploadConsentDone = !!localStorage.getItem('mohamy_upload_consent_v1');
    this.loadHistory();
    this.loadSessions();
  }

  acceptConsent(): void {
    if (!this.consentAge || !this.consentPrivacy) return;
    localStorage.setItem(
      'mohamy_consent_v1',
      JSON.stringify({ accepted_at: new Date().toISOString() })
    );
    this.needsConsent = false;
    this.http
      .post(this.consentUrl, {
        session_id: this.sessionId,
        owner_id: this.ownerId,
        kind: 'privacy_cross_border_age',
        accepted: true,
      })
      .subscribe({ next: () => {}, error: () => {} });
  }

  reportMessage(index: number): void {
    this.reportingIndex = index;
    this.reportText = '';
  }

  cancelReport(): void {
    this.reportingIndex = null;
    this.reportText = '';
  }

  submitReport(): void {
    if (this.reportingIndex === null) return;
    const idx = this.reportingIndex;
    const msg = this.chatHistory[idx];
    const ref = msg ? (msg.text || '').slice(0, 120) : '';
    this.http
      .post(this.reportUrl, {
        session_id: this.sessionId,
        owner_id: this.ownerId,
        reason: this.reportText.trim() || 'بدون تفاصيل',
        message_ref: ref,
      })
      .subscribe({
        next: () => {
          this.reportingIndex = null;
          this.reportText = '';
          this.chatHistory.push({
            sender: 'bot',
            text: '✅ شكراً لك. تم تسجيل الملاحظة وسنراجعها.',
          });
          this.cdr.detectChanges();
        },
        error: () => {
          this.reportingIndex = null;
          this.reportText = '';
          this.chatHistory.push({
            sender: 'bot',
            text: 'تعذّر إرسال الملاحظة. حاول مرة أخرى.',
          });
          this.cdr.detectChanges();
        },
      });
  }

  private loadHistory(): void {
    this.chatHistory = [];
    this.lastArticles = [];
    this.http
      .get<any>(
        `${this.historyUrl}?session_id=${encodeURIComponent(this.sessionId)}` +
        `&owner_id=${encodeURIComponent(this.ownerId)}&limit=50`
      )
      .subscribe({
        next: (resp) => {
          if (!resp?.turns?.length) {
            this.cdr.detectChanges();
            return;
          }
          for (const turn of resp.turns) {
            if (turn.user) {
              this.chatHistory.push({ sender: 'user', text: turn.user });
            }
            if (turn.bot) {
              this.chatHistory.push({
                sender: 'bot',
                text: turn.bot,
                articles: Array.isArray(turn.articles) ? turn.articles : [],
              });
            }
          }
          if (this.chatHistory.length > 0) {
            const last = this.chatHistory[this.chatHistory.length - 1];
            this.lastArticles = last.articles || [];
          }
          this.cdr.detectChanges();
        },
        error: () => {
          /* best-effort */
        },
      });
  }

  loadSessions(): void {
    this.http.get<any>(
      `${this.sessionsUrl}?owner_id=${encodeURIComponent(this.ownerId)}&limit=50`
    ).subscribe({
      next: (resp) => {
        this.sessions = Array.isArray(resp?.sessions) ? resp.sessions : [];
        this.cdr.detectChanges();
      },
      error: () => {
        /* best-effort */
      },
    });
  }

  newChat(): void {
    const fresh = this.generateSessionId();
    this.sessionId = fresh;
    localStorage.setItem('mohamy_session_id', fresh);
    this.chatHistory = [];
    this.lastArticles = [];
    this.clarificationOptions = [];
    this.userInput = '';
    this.cdr.detectChanges();
  }

  switchSession(id: string): void {
    if (!id || id === this.sessionId) return;
    this.sessionId = id;
    localStorage.setItem('mohamy_session_id', id);
    this.loadHistory();
  }

  confirmDelete(event: Event, session: ChatSession): void {
    event.stopPropagation();
    this.pendingDeleteSession = session;
  }

  cancelDelete(): void {
    this.pendingDeleteSession = null;
  }

  proceedDelete(): void {
    const session = this.pendingDeleteSession;
    if (!session) return;
    const id = session.session_id;
    this.pendingDeleteSession = null;
    this.http.delete<any>(
      `${this.sessionsUrl}/${encodeURIComponent(id)}` +
      `?owner_id=${encodeURIComponent(this.ownerId)}`
    ).subscribe({
      next: (resp) => {
        console.log('delete_session:', resp);
        this.sessions = this.sessions.filter((s) => s.session_id !== id);
        if (id === this.sessionId) {
          this.newChat();
        }
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('delete_session failed', err);
        alert('تعذّر حذف المحادثة. تأكد من تشغيل الخادم.');
      },
    });
  }

  toggleSidebar(): void {
    this.sidebarOpen = !this.sidebarOpen;
  }

  sendMessage(): void {
    if (this.needsConsent) return;
    const query = this.userInput.trim();
    if (!query || this.isLoading) {
      return;
    }

    this.chatHistory.push({ sender: 'user', text: query });
    this.userInput = '';
    this.isLoading = true;

    this.chatHistory.push({
      sender: 'bot',
      text: 'جاري البحث في قاعدة البيانات القانونية...',
    });

    this.currentRequest = this.http
      .post<AskResponse>(this.apiUrl, {
        query,
        session_id: this.sessionId,
        owner_id: this.ownerId,
      })
      .subscribe({
        next: (resp) => {
          console.log('Backend response:', resp);
          this.chatHistory.pop();
          this.handleResponse(resp);
          this.isLoading = false;
          this.currentRequest = null;
          this.loadSessions();
          this.cdr.detectChanges();
        },
        error: (err) => {
          console.error(err);
          this.chatHistory.pop();
          this.chatHistory.push({
            sender: 'bot',
            text: 'حدث خطأ في الاتصال بالخادم. حاول مرة أخرى.',
          });
          this.isLoading = false;
          this.currentRequest = null;
          this.cdr.detectChanges();
        },
      });
  }

  stopGeneration(): void {
    if (this.currentRequest) {
      this.currentRequest.unsubscribe();
      this.currentRequest = null;
    }
    // Pop the "جاري البحث..." loading bubble.
    if (
      this.chatHistory.length > 0 &&
      this.chatHistory[this.chatHistory.length - 1].sender === 'bot'
    ) {
      const last = this.chatHistory[this.chatHistory.length - 1].text || '';
      if (last.startsWith('جاري البحث')) {
        this.chatHistory.pop();
      }
    }
    this.chatHistory.push({
      sender: 'bot',
      text: 'تم إيقاف التوليد. يمكنك إعادة الإرسال أو تعديل سؤالك.',
    });
    this.isLoading = false;
    this.cdr.detectChanges();
  }

  editMessage(index: number): void {
    if (this.isLoading) return;
    const msg = this.chatHistory[index];
    if (!msg || msg.sender !== 'user') return;
    // Put the message text back into the input
    this.userInput = msg.text;
    // Count how many turn pairs (user+bot) we'll discard so we can also
    // delete them from the persistent runtime DB.
    const toRemove = this.chatHistory.length - index;
    const userPairsAfter = this.chatHistory
      .slice(index)
      .filter((m) => m.sender === 'user').length;
    // Trim local chat history from the edited message onwards.
    this.chatHistory = this.chatHistory.slice(0, index);
    // Trim the persisted history too (best-effort).
    if (userPairsAfter > 0) {
      this.http
        .delete(
          `${environment.apiUrl}/history/last?session_id=${encodeURIComponent(
            this.sessionId
          )}&owner_id=${encodeURIComponent(this.ownerId)}&count=${userPairsAfter}`
        )
        .subscribe({
          next: () => this.loadSessions(),
          error: () => {},
        });
    }
    this.cdr.detectChanges();
  }

  onKeyPress(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey && this.userInput.trim()) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  chooseOption(option: string): void {
    if (option === 'عرض نصوص المواد') {
      this.showArticleDetails();
      return;
    }

    if (this.isLoading) return;

    this.chatHistory.push({ sender: 'user', text: option });
    this.clarificationOptions = [];
    this.isLoading = true;

    this.http
      .post<AskResponse>(this.apiUrl, {
        query: option,
        session_id: this.sessionId,
        owner_id: this.ownerId,
      })
      .subscribe({
        next: (resp) => {
          console.log('Backend response (option):', resp);
          this.handleResponse(resp);
          this.isLoading = false;
          this.cdr.detectChanges();
        },
        error: (err) => {
          console.error(err);
          this.chatHistory.push({
            sender: 'bot',
            text: 'حدث خطأ في الاتصال بالخادم. حاول مرة أخرى.',
          });
          this.isLoading = false;
          this.cdr.detectChanges();
        },
      });
  }

  private showArticleDetails(): void {
    this.chatHistory.push({ sender: 'user', text: 'عرض تفاصيل المواد' });

    if (this.lastArticles.length === 0) {
      this.chatHistory.push({
        sender: 'bot',
        text: 'عذراً، لا توجد مواد محفوظة لعرض التفاصيل.',
      });
      return;
    }

    const detailsText = this.lastArticles
      .map((law, idx) => {
        const title = law.titel || law.law_name || 'بدون عنوان';
        const details = law.details || 'لا يوجد نص متوفر.';
        return `📄 <strong>مادة ${idx + 1}: ${title}</strong>\n${details}`;
      })
      .join('\n\n---\n\n');

    this.chatHistory.push({
      sender: 'bot',
      text: 'تفاصيل المواد القانونية كاملة:\n\n' + detailsText,
    });
  }

  private handleResponse(resp: AskResponse): void {
    const stage =
      resp.stage ||
      (resp.needs_clarification ? 'clarification' : 'final_answer');

    if (stage === 'clarification') {
      const q =
        resp.clarification_question ||
        'سؤالك عام. من فضلك اختر موضوعاً أكثر تحديداً من الاختيارات التالية.';
      this.chatHistory.push({ sender: 'bot', text: q });
      this.clarificationOptions = resp.clarification_options || [];
      return;
    }

    this.clarificationOptions = [];

    if (stage === 'no_results') {
      const msg = resp.message || 'لم أجد إجابة مباشرة في قاعدة البيانات.';
      this.chatHistory.push({ sender: 'bot', text: msg });
      return;
    }

    if (stage === 'error' || stage === 'selection_error') {
      const msg =
        resp.message || 'حدث خطأ أثناء معالجة سؤالك. حاول مرة أخرى.';
      this.chatHistory.push({ sender: 'bot', text: msg });
      return;
    }

    this.lastArticles = resp.articles || resp.laws || [];

    const chunks: string[] = [];

    if (resp.verification?.law_existence_warning) {
      const w = resp.verification.law_existence_warning;
      const suggList = (w.suggestions || [])
        .slice(0, 3)
        .map(
          (s) =>
            `• قانون رقم <strong>${s.T_No}</strong> لسنة <strong>${s.T_Year}</strong>` +
            (s.law_name ? ` — ${s.law_name}` : '')
        )
        .join('\n');
      const banner =
        '<div style="background:#7c2d12;color:#fff;padding:10px 12px;border-radius:8px;margin-bottom:8px;border:2px solid #fdba74"><strong>🚨 تنبيه تشريعي:</strong> القانون الذي ذكرته (<strong>' +
        w.user_cited +
        '</strong>) <strong>غير موجود</strong> في قاعدة البيانات الرسمية للقوانين المصرية.' +
        (suggList ? '\n<strong>التشريع الصحيح المرتبط بالموضوع:</strong>\n' + suggList : '') +
        '\n<em>الإجابة أدناه ستستند إلى التشريع الصحيح.</em></div>';
      chunks.push(banner);
    }

    if (resp.verification?.cancelled_warning) {
      const cancelledList = this.lastArticles
        .filter((a) => a.is_cancelled)
        .map((a) => `• ${a.titel || a.law_name || ''}`)
        .join('\n');
      const banner =
        '<div style="background:#7f1d1d;color:#fff;padding:8px 12px;border-radius:8px;margin-bottom:8px"><strong>⚠️ تحذير إلغاء:</strong> بعض المواد المستندة إليها قد تكون <strong>ملغاة</strong>. يُرجى التحقق من النص النافذ قبل الاعتماد على الإجابة.' +
        (cancelledList ? '\n' + cancelledList : '') +
        '</div>';
      chunks.push(banner);
    }

    if (resp.verification?.precedent_warning) {
      const refs = (resp.verification?.precedent_refs || []).slice(0, 4);
      const refList = refs.map((r) => `• ${r}`).join('\n');
      const banner =
        '<div style="background:#78350f;color:#fff;padding:8px 12px;border-radius:8px;margin-bottom:8px"><strong>⚖️ تنبيه قضائي:</strong> توجد أحكام دستورية أو قضائية ذات صلة قد تؤثر على تطبيق المادة. راجع التفاصيل في الإجابة قبل الاعتماد عليها.' +
        (refList ? '\n' + refList : '') +
        '</div>';
      chunks.push(banner);
    }

    if (resp.chosen_categories && resp.chosen_categories.length > 0) {
      const catText =
        '📂 تم تصفية النتائج حسب التصنيفات:\n- ' +
        resp.chosen_categories.join('\n- ');
      chunks.push(catText);
    }

    if (resp.answer) {
      chunks.push(resp.answer.trim());
    } else if (resp.summary) {
      chunks.push(resp.summary.trim());
    } else if (resp.message) {
      chunks.push(resp.message.trim());
    }

    const finalText =
      chunks.length > 0
        ? chunks.join('\n\n')
        : 'لم أستطع توليد إجابة مناسبة لهذا السؤال.';

    this.chatHistory.push({
      sender: 'bot',
      text: finalText,
      articles: this.lastArticles.length > 0 ? this.lastArticles : undefined,
    });
  }

  explainArticle(article: Law): void {
    if (this.isLoading || !article || article.table == null || article.id == null) return;

    const title = article.titel || article.law_name || 'مادة قانونية';
    this.chatHistory.push({ sender: 'user', text: `عرض شرح: ${title}` });
    this.isLoading = true;
    this.chatHistory.push({ sender: 'bot', text: 'جاري إعداد الشرح...' });

    this.http
      .post<any>(this.explainUrl, {
        session_id: this.sessionId,
        owner_id: this.ownerId,
        table: article.table,
        article_id: article.id,
      })
      .subscribe({
        next: (resp) => {
          this.chatHistory.pop();
          this.chatHistory.push({
            sender: 'bot',
            text: resp?.explanation || 'لم يتم توليد شرح.',
          });
          this.isLoading = false;
          this.cdr.detectChanges();
        },
        error: (err) => {
          console.error('explain_article error', err);
          this.chatHistory.pop();
          this.chatHistory.push({
            sender: 'bot',
            text: 'تعذّر تحميل الشرح. حاول مرة أخرى.',
          });
          this.isLoading = false;
          this.cdr.detectChanges();
        },
      });
  }

  toggleBrowseModal(): void {
    this.showBrowseModal = !this.showBrowseModal;
    if (this.showBrowseModal && this.lawCategories.length === 0) {
      this.fetchCategories();
    }
  }

  closeBrowseModal(): void {
    this.showBrowseModal = false;
  }

  fetchCategories(): void {
    this.isLoadingCategories = true;
    const listUrl = this.apiUrl.replace('/ask', '/laws');

    this.http.get<any>(listUrl).subscribe({
      next: (data) => {
        console.log('Categories fetched:', data);
        if (data && data.categories) {
          this.lawCategories = data.categories;
        }
        this.isLoadingCategories = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Failed to fetch laws', err);
        this.isLoadingCategories = false;
        this.cdr.detectChanges();
      }
    });
  }

  onFileSelected(event: any): void {
    if (this.needsConsent) return;
    const file: File = event.target.files[0];
    if (!file) return;
    if (!this.uploadConsentDone) {
      this.pendingUploadFile = file;
      return;
    }
    this.uploadDocument(file);
  }

  acceptUploadConsent(): void {
    localStorage.setItem(
      'mohamy_upload_consent_v1',
      JSON.stringify({ accepted_at: new Date().toISOString() })
    );
    this.uploadConsentDone = true;
    this.http
      .post(this.consentUrl, {
        session_id: this.sessionId,
        owner_id: this.ownerId,
        kind: 'upload',
        accepted: true,
      })
      .subscribe({ next: () => {}, error: () => {} });
    if (this.pendingUploadFile) {
      const f = this.pendingUploadFile;
      this.pendingUploadFile = null;
      this.uploadDocument(f);
    }
  }

  cancelUploadConsent(): void {
    this.pendingUploadFile = null;
  }

  uploadDocument(file: File): void {
    if (this.isUploading) return;

    this.chatHistory.push({ sender: 'user', text: `📄 جاري رفع المستند: ${file.name}` });
    this.isUploading = true;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('session_id', this.sessionId);
    formData.append('owner_id', this.ownerId);

    this.http.post<any>(this.uploadUrl, formData).subscribe({
      next: (response) => {
        console.log('Upload response:', response);

        if (response.status === 'success') {
          const analysisText = `📄 تحليل المستند: ${response.filename}\n\n${response.analysis}`;
          this.chatHistory.push({ sender: 'bot', text: analysisText });
        } else {
          this.chatHistory.push({ sender: 'bot', text: `❌ فشل معالجة المستند: ${response.message}` });
        }

        this.isUploading = false;
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Upload error:', err);
        this.chatHistory.push({ sender: 'bot', text: '❌ حدث خطأ أثناء رفع المستند. حاول مرة أخرى.' });
        this.isUploading = false;
        this.cdr.detectChanges();
      }
    });
  }

  isRecording = false;
  recognition: any;

  startVoiceRecognition(): void {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const v = window as any;
      const SpeechRecognition = v.webkitSpeechRecognition || v.SpeechRecognition;
      this.recognition = new SpeechRecognition();
      this.recognition.lang = 'ar-EG';
      this.recognition.continuous = false;
      this.recognition.interimResults = false;

      this.recognition.onstart = () => {
        this.isRecording = true;
        this.cdr.detectChanges();
      };

      this.recognition.onend = () => {
        this.isRecording = false;
        this.cdr.detectChanges();
      };

      this.recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        this.userInput = transcript;
        this.cdr.detectChanges();
      };

      this.recognition.onerror = (event: any) => {
        console.error('Speech recognition error', event);
        this.isRecording = false;
        this.cdr.detectChanges();
      };

      this.recognition.start();
    } else {
      alert('عذراً، متصفحك لا يدعم خاصية التحدث الصوتي.');
    }
  }
}
