import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';

@Component({
  selector: 'app-terms',
  standalone: true,
  imports: [CommonModule, RouterModule],
  templateUrl: './terms.component.html',
})
export class TermsComponent {
  lastUpdated = '2026-05-14';
  openSection: number | null = 1;

  toggle(i: number): void {
    this.openSection = this.openSection === i ? null : i;
  }

  isOpen(i: number): boolean {
    return this.openSection === i;
  }
}
