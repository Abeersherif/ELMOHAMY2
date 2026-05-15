import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';

@Component({
  selector: 'app-privacy',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './privacy.component.html',
})
export class PrivacyComponent {
  lastUpdated = '2026-05-14';
  openSection: number | null = 1;

  toggle(i: number): void {
    this.openSection = this.openSection === i ? null : i;
  }

  isOpen(i: number): boolean {
    return this.openSection === i;
  }
}
