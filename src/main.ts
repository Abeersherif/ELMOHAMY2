import { bootstrapApplication } from '@angular/platform-browser';
import { AppComponent } from './app/app.component';  // Import the standalone AppComponent
import { appConfig } from './app/app.config';        // Import the appConfig

// Bootstrap the application with the appConfig
bootstrapApplication(AppComponent, appConfig)
  .catch(err => console.error(err));
