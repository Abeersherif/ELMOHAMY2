import { Routes } from '@angular/router';
import { IntroComponent } from './intro/intro';
import { HomeComponent } from './home/home.component';
import { QaComponent } from './qa/qa.component';

export const routes: Routes = [
  { path: '', component: IntroComponent },
  { path: 'home', component: HomeComponent },
  { path: 'qa', component: QaComponent }
];
