import { Routes } from '@angular/router';
import { Dashboard } from './dashboard/dashboard';
import { Investors } from './investors/investors';
import { Bankers } from './bankers/bankers';
import { InvestorDetails } from './investor-details/investor-details';

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { 
    path: 'dashboard', 
    component: Dashboard,
    children: [
      { path: '', redirectTo: 'investors', pathMatch: 'full' },
      { path: 'investors', component: Investors },
      { path: 'bankers', component: Bankers },
      { path: 'investor/details', component: InvestorDetails },
      { path: 'investors/details', redirectTo: 'investor/details' }
    ]
  },
  { path: 'investor/details', redirectTo: 'dashboard/investor/details' },
  { path: 'investors/details', redirectTo: 'dashboard/investor/details' }
];
