import { Component, ChangeDetectorRef } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';

interface ChatMessage {
  sender: 'user' | 'bot';
  text: string;
}

interface Law {
  id: number;
  law_name: string | null;
  main_category: string | null;
  number: string | null;
  titel: string | null;
  details: string | null;
  source_type: string | null;
  Tash_id: number | null;
  Date_Tash: string | null;
  table?: string | null;
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
  };
  related_topics?: string[];
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

@Component({
  selector: 'app-qa',
  standalone: true,
  templateUrl: './qa.component.html',
  styleUrls: ['./qa.component.css'],
  imports: [CommonModule, FormsModule],
})
export class QaComponent {
  apiUrl = 'http://127.0.0.1:8000/ask';
  uploadUrl = 'http://127.0.0.1:8000/upload_document';

  userInput = '';
  chatHistory: ChatMessage[] = [];
  clarificationOptions: string[] = [];
  isLoading = false;
  isUploading = false;

  showBrowseModal = false;
  lawCategories: any[] = [];
  isLoadingCategories = false;

  relatedTopics: string[] = [];
  lastArticles: Law[] = [];

  private sessionId: string;

  constructor(
    private http: HttpClient,
    private cdr: ChangeDetectorRef
  ) {
    const saved = localStorage.getItem('mohamy_session_id');
    if (saved) {
      this.sessionId = saved;
    } else {
      this.sessionId = 'web-' + Date.now().toString();
      localStorage.setItem('mohamy_session_id', this.sessionId);
    }
  }

  sendMessage(): void {
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

    this.http
      .post<AskResponse>(this.apiUrl, {
        query,
        session_id: this.sessionId,
      })
      .subscribe({
        next: (resp) => {
          console.log('Backend response:', resp);
          this.chatHistory.pop();
          this.handleResponse(resp);
          this.isLoading = false;
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
          this.cdr.detectChanges();
        },
      });
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

    this.relatedTopics = resp.related_topics || [];

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

    if (this.lastArticles.length > 0) {
      const lawsText = this.formatLawsCompact(this.lastArticles);
      if (lawsText.trim().length > 0) {
        chunks.push(lawsText);

        if (!this.relatedTopics.includes('عرض نصوص المواد')) {
          this.relatedTopics.unshift('عرض نصوص المواد');
        }
      }
    }

    const finalText =
      chunks.length > 0
        ? chunks.join('\n\n')
        : 'لم أستطع توليد إجابة مناسبة لهذا السؤال.';

    this.chatHistory.push({
      sender: 'bot',
      text: finalText,
    });
  }

  private formatLawsCompact(laws: Law[]): string {
    if (!laws || laws.length === 0) return '';

    const lines = laws.map((law, idx) => {
      const index = idx + 1;
      const name = law.law_name || law.titel || '';
      const num = law.number ? ` (رقم/مادة: ${law.number})` : '';
      const cat = law.main_category ? ` – ${law.main_category}` : '';
      return `${index}) ${name}${num}${cat}`.trim();
    });

    return (
      '<strong>هذه أمثلة من النصوص القانونية ذات الصلة بسؤالك:</strong>\n' + lines.join('\n')
    );
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
    const file: File = event.target.files[0];
    if (file) {
      this.uploadDocument(file);
    }
  }

  uploadDocument(file: File): void {
    if (this.isUploading) return;

    this.chatHistory.push({ sender: 'user', text: `📄 جاري رفع المستند: ${file.name}` });
    this.isUploading = true;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('session_id', this.sessionId);

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
