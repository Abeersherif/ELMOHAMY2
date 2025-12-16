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
  title = 'المحامي المصري';
  showGate = true;

  ngOnInit() {
    // Global Gate Animation
    setTimeout(() => {
      this.showGate = false;
    }, 4000); // 4 seconds total to clear safely
  }
}
