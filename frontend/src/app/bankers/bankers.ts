import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { EsgService, FrameworkDocument } from '../services/esg.service';
import { SVGS } from '../constants/svgs';
import { ESG_FRAMEWORKS } from '../constants/frameworks';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-bankers',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './bankers.html',
  styleUrl: './bankers.css',
})
export class Bankers implements OnInit {
  svgs = SVGS;
  frameworkOptions = [...ESG_FRAMEWORKS, 'Other Custom Framework'];
  private esgService = inject(EsgService);

  questionnaires = signal<{ basic: any[]; comprehensive: any[] } | null>(null);
  frameworkDocs = signal<FrameworkDocument[]>([]);
  isLoading = signal(true);
  error = signal<string | null>(null);

  // Main navigation tab: 'questionnaires' or 'frameworks'
  mainViewTab = signal<'questionnaires' | 'frameworks'>('questionnaires');
  activeTab = signal<'basic' | 'comprehensive'>('basic');
  searchQuery = signal('');

  // Questionnaire Framework Filter
  questionnaireFrameworkOptions = ESG_FRAMEWORKS;
  selectedQuestionnaireFramework = signal<string>(ESG_FRAMEWORKS[0]);

  // Upload Framework Modal State
  isUploadModalOpen = signal(false);
  isUploading = signal(false);
  selectedFrameworkName = signal(ESG_FRAMEWORKS[0]);
  customFrameworkName = signal('');
  frameworkDescription = signal('');
  selectedFile = signal<File | null>(null);
  uploadError = signal<string | null>(null);
  uploadSuccess = signal<string | null>(null);

  async ngOnInit() {
    await this.loadData();
  }

  async loadData() {
    this.isLoading.set(true);
    try {
      const [qData, docsData] = await Promise.all([
        this.esgService.getQuestionnaires().catch(() => null),
        this.esgService.getFrameworkDocuments().catch(() => [])
      ]);
      if (qData) this.questionnaires.set(qData);
      this.frameworkDocs.set(docsData || []);
    } catch (err) {
      console.error('Failed to load admin data:', err);
      this.error.set('Failed to load reference data from backend server.');
    } finally {
      this.isLoading.set(false);
    }
  }

  openUploadModal() {
    this.selectedFrameworkName.set(ESG_FRAMEWORKS[0]);
    this.customFrameworkName.set('');
    this.frameworkDescription.set('');
    this.selectedFile.set(null);
    this.uploadError.set(null);
    this.uploadSuccess.set(null);
    this.isUploadModalOpen.set(true);
  }

  closeUploadModal() {
    this.isUploadModalOpen.set(false);
  }

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.selectedFile.set(input.files[0]);
      this.uploadError.set(null);
    }
  }

  onFileDrop(event: DragEvent) {
    event.preventDefault();
    if (event.dataTransfer && event.dataTransfer.files.length > 0) {
      this.selectedFile.set(event.dataTransfer.files[0]);
      this.uploadError.set(null);
    }
  }

  onDragOver(event: DragEvent) {
    event.preventDefault();
  }

  removeSelectedFile() {
    this.selectedFile.set(null);
  }

  getEffectiveFrameworkName(): string {
    if (this.selectedFrameworkName() === 'Other Custom Framework') {
      return this.customFrameworkName().trim() || 'Custom Standard Framework';
    }
    return this.selectedFrameworkName();
  }

  async handleUploadFramework() {
    const file = this.selectedFile();
    const frameworkName = this.getEffectiveFrameworkName();

    if (!file) {
      this.uploadError.set('Please select a framework document file to upload.');
      return;
    }

    if (!frameworkName) {
      this.uploadError.set('Please select or enter the Framework Name.');
      return;
    }

    this.isUploading.set(true);
    this.uploadError.set(null);

    try {
      await this.esgService.uploadFrameworkDocument(
        frameworkName,
        file,
        this.frameworkDescription()
      );
      this.uploadSuccess.set(`Framework document "${file.name}" uploaded successfully!`);
      
      // Refresh framework list and switch to frameworks view
      const docsData = await this.esgService.getFrameworkDocuments().catch(() => []);
      this.frameworkDocs.set(docsData || []);
      this.mainViewTab.set('frameworks');

      setTimeout(() => {
        this.closeUploadModal();
      }, 1200);
    } catch (err: any) {
      console.error('Upload framework document failed:', err);
      this.uploadError.set(err?.error?.detail || 'Failed to upload framework document. Please try again.');
    } finally {
      this.isUploading.set(false);
    }
  }

  async deleteFrameworkDoc(docId: string, event: Event) {
    event.stopPropagation();
    if (!confirm('Are you sure you want to delete this framework document?')) {
      return;
    }
    try {
      await this.esgService.deleteFrameworkDocument(docId);
      this.frameworkDocs.update(docs => docs.filter(d => d.docId !== docId));
    } catch (err) {
      console.error('Failed to delete framework document:', err);
      alert('Failed to delete framework document.');
    }
  }

  downloadFrameworkDoc(docId: string, event: Event) {
    event.stopPropagation();
    this.esgService.downloadFrameworkDocument(docId);
  }

  getFilteredFrameworkDocs() {
    const query = this.searchQuery().trim().toLowerCase();
    const docs = this.frameworkDocs();
    if (!query) return docs;
    return docs.filter(
      d =>
        d.frameworkName.toLowerCase().includes(query) ||
        d.fileName.toLowerCase().includes(query) ||
        (d.description && d.description.toLowerCase().includes(query))
    );
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
