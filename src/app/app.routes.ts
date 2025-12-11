import { Routes } from '@angular/router';
import { HomeComponent } from './home/home.component';
import { QaComponent } from './qa/qa.component';

export const routes: Routes = [
  { path: '', component: HomeComponent },
  { path: 'chat', component: QaComponent },
  { path: '**', redirectTo: '' }
];
