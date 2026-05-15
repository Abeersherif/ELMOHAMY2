import { Component } from '@angular/core';
import { CommonModule } from '@angular/common'; // Import CommonModule for *ngIf
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { QaComponent } from './qa/qa.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive, QaComponent],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.css']
})
export class AppComponent {
  title = 'المساعد القانوني المصري';
  year = new Date().getFullYear();
  showGate = !sessionStorage.getItem('mohamy_gate_shown');

  ngOnInit() {
    if (!this.showGate) return;
    setTimeout(() => {
      this.showGate = false;
      sessionStorage.setItem('mohamy_gate_shown', '1');
    }, 1500);
  }
}
