import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class LegalAgentService {
  private apiUrl = 'http://127.0.0.1:8000/ask';

  constructor(private http: HttpClient) { }

  askQuestion(question: string): Observable<any> {
    const sessionId = 'session_' + Date.now(); // Generate unique session ID
    const body = { query: question, session_id: sessionId };
    return this.http.post<any>(this.apiUrl, body);
  }
}