import { Component, signal, inject, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { EsgService } from '../services/esg.service';
import { SVGS } from '../constants/svgs';

@Component({
  selector: 'app-investors',
  imports: [RouterLink],
  templateUrl: './investors.html',
  styleUrl: './investors.css',
})
export class Investors {
  svgs = SVGS;
  private esgService = inject(EsgService);
  
  requests = this.esgService.getRequests();

  totalSubmitted = computed(() => this.requests().length);
  totalPending = computed(() => 
    this.requests().filter(r => r.status === 'Pending Review').length
  );
  totalDocuments = computed(() => 
    this.requests().reduce((acc, r) => acc + r.numDocs, 0)
  );
  totalCompleted = computed(() => 
    this.requests().filter(r => r.status === 'Completed' || r.status === 'Approved').length
  );

  isUploadModalOpen = signal(false);
  isUploading = signal(false);
  selectedYear = signal(2026);
  selectedModelEngine = signal<string>('gemini-3.5');
  selectedReportName = signal<string>('');
  selectedFiles = signal<File[]>([]);

  onFileSelected(event: any) {
    const fileList = event.target.files as FileList;
    if (fileList && fileList.length > 0) {
      const filesArray = Array.from(fileList);
      this.selectedFiles.update(existing => [...existing, ...filesArray]);
    }
  }

  removeSelectedFile(index: number) {
    this.selectedFiles.update(files => files.filter((_, i) => i !== index));
  }

  async onUploadSubmit() {
    const files = this.selectedFiles();
    const year = this.selectedYear();
    const model = this.selectedModelEngine();
    const reportName = this.selectedReportName();
    
    if (!reportName.trim()) {
      alert('Please enter a name for the report.');
      return;
    }

    if (files.length === 0) {
      alert('Please select at least one document to upload.');
      return;
    }

    this.isUploading.set(true);
    try {
      await this.esgService.uploadDocuments(year, files, model, undefined, reportName);
      // Reset state
      this.selectedFiles.set([]);
      this.selectedReportName.set('');
      this.isUploadModalOpen.set(false);
    } catch (err) {
      console.error('Upload failed:', err);
      alert('Failed to upload files. Please try again.');
    } finally {
      this.isUploading.set(false);
    }
  }

  isDeleteModalOpen = signal(false);
  requestToDelete = signal<string | null>(null);

  onDeleteRequest(id: string) {
    this.requestToDelete.set(id);
    this.isDeleteModalOpen.set(true);
  }

  async confirmDelete() {
    const id = this.requestToDelete();
    if (id) {
      this.isDeleteModalOpen.set(false);
      try {
        await this.esgService.deleteRequest(id);
      } catch (err) {
        console.error('Delete failed:', err);
        alert('Failed to delete request. Please try again.');
      } finally {
        this.requestToDelete.set(null);
      }
    }
  }
}
