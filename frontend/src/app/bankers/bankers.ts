import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { EsgService } from '../services/esg.service';
import { SVGS } from '../constants/svgs';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-bankers',
  imports: [CommonModule, FormsModule],
  templateUrl: './bankers.html',
  styleUrl: './bankers.css',
})
export class Bankers implements OnInit {
  svgs = SVGS;
  private esgService = inject(EsgService);

  questionnaires = signal<{ basic: any[]; comprehensive: any[] } | null>(null);
  isLoading = signal(true);
  error = signal<string | null>(null);
  activeTab = signal<'basic' | 'comprehensive'>('basic');
  searchQuery = signal('');

  async ngOnInit() {
    try {
      const data = await this.esgService.getQuestionnaires();
      this.questionnaires.set(data);
    } catch (err) {
      console.error('Failed to load questionnaires:', err);
      this.error.set('Failed to load questionnaires from the backend. Please ensure the server is running.');
    } finally {
      this.isLoading.set(false);
    }
  }

  getFilteredSections() {
    const q = this.questionnaires();
    if (!q) return [];

    const sections = this.activeTab() === 'basic' ? q.basic : q.comprehensive;
    const query = this.searchQuery().trim().toLowerCase();
    if (!query) return sections;

    return sections
      .map((sec: any) => {
        const filteredQuestions = sec.questions.filter((qst: string) =>
          qst.toLowerCase().includes(query)
        );
        const matchesTitle = sec.title.toLowerCase().includes(query);
        if (matchesTitle || filteredQuestions.length > 0) {
          return {
            ...sec,
            questions: filteredQuestions.length > 0 ? filteredQuestions : sec.questions,
          };
        }
        return null;
      })
      .filter((sec: any) => sec !== null);
  }
}
