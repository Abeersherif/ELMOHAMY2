import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { HttpClientModule } from '@angular/common/http';
import { AppComponent } from './app.component';
import { QaComponent } from './qa/qa.component';

@NgModule({
  declarations: [
  ],
  imports: [
    BrowserModule,
    HttpClientModule,
    AppComponent,
    QaComponent
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule { }
