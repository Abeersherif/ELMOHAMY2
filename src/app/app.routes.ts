import { Routes } from '@angular/router';
import { HomeComponent } from './home/home.component';
import { QaComponent } from './qa/qa.component';
import { PrivacyComponent } from './privacy/privacy.component';
import { TermsComponent } from './terms/terms.component';

export const routes: Routes = [
  { path: '', component: HomeComponent },
  { path: 'chat', component: QaComponent },
  { path: 'privacy', component: PrivacyComponent },
  { path: 'terms', component: TermsComponent },
  { path: '**', redirectTo: '' }
];
