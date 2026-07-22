import { Component, OnInit, inject, signal, computed, effect } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { EsgService, EsgRequest } from '../services/esg.service';
import { SVGS } from '../constants/svgs';

@Component({
  selector: 'app-investor-details',
  imports: [RouterLink, CommonModule],
  templateUrl: './investor-details.html',
  styleUrl: './investor-details.css',
})
export class InvestorDetails implements OnInit {
  svgs = SVGS;
  private route = inject(ActivatedRoute);
  private esgService = inject(EsgService);
  private sanitizer = inject(DomSanitizer);
  
  requestId = signal<string | null>(null);
  request = signal<EsgRequest | undefined>(undefined);

  constructor() {
    effect(() => {
      const id = this.requestId();
      const list = this.esgService.getRequests()();
      if (id && list.length > 0) {
        const found = list.find(r => r.id === id);
        if (found) {
          this.request.set(found);
          this.loadNormalizedJson();
        }
      }
    });
  }

  isUploadModalOpen = signal(false);
  isUploading = signal(false);
  selectedFiles = signal<File[]>([]);

  normalizedReportJson = signal<any>(null);
  activeSectionTab = signal<'details' | 'trends'>('details');

  searchQuery = signal<string>('');

  filteredReportData = computed(() => {
    const query = this.searchQuery().toLowerCase().trim();
    const req = this.request();
    if (!req || !req.reportData) return [];
    
    const dataList = Array.isArray(req.reportData) 
      ? req.reportData 
      : ((req.reportData as any).questionnaire_data || []);
      
    if (!query) return dataList;
    
    return dataList.filter((item: any) => 
      (item?.question && item.question.toLowerCase().includes(query)) ||
      (item?.answer && item.answer.toLowerCase().includes(query))
    );
  });

  onSearchQueryChange(event: any) {
    this.searchQuery.set(event.target.value);
  }

  reportStats = computed(() => {
    const req = this.request();
    if (!req || !req.reportData) {
      return null;
    }
    
    const dataList = Array.isArray(req.reportData) 
      ? req.reportData 
      : ((req.reportData as any).questionnaire_data || null);
      
    if (!dataList || !dataList.length) {
      return null;
    }
    
    const total = dataList.length;
    const answered = dataList.filter((item: any) => {
      if (!item.answer) return false;
      const ans = item.answer.toLowerCase().trim();
      return ans !== '' && 
             ans !== 'missing' && 
             ans !== 'not specified' && 
             ans !== 'error querying document rag' &&
             ans !== 'not disclosed';
    }).length;
    
    const percentage = total > 0 ? Math.round((answered / total) * 100) : 0;
    
    return {
      answered,
      total,
      percentage
    };
  });

  async loadNormalizedJson() {
    const req = this.request();
    if (!req) return;
    
    const hasReportData = req.reportData && (
      Array.isArray(req.reportData) 
        ? req.reportData.length > 0 
        : !!(req.reportData as any).questionnaire_data
    );

    if (req.status === 'Completed' || req.status === 'Approved' || hasReportData) {
      try {
        const data = await this.esgService.getReportNormalizedJson(req.id);
        this.normalizedReportJson.set(data);
      } catch (err) {
        console.warn('Failed to load normalized JSON data:', err);
        this.normalizedReportJson.set(null);
      }
    } else {
      this.sanitizer.bypassSecurityTrustResourceUrl(''); // dummy reference
      this.normalizedReportJson.set(null);
    }
  }

  ngOnInit() {
    this.route.queryParams.subscribe(params => {
      const id = params['id'];
      if (id) {
        this.requestId.set(id);
      }
    });
  }

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
    const req = this.request();
    
    if (files.length === 0) {
      alert('Please select at least one document to upload.');
      return;
    }
    
    if (!req) {
      alert('No active request found.');
      return;
    }

    this.isUploading.set(true);
    try {
      await this.esgService.uploadDocuments(req.year, files, req.model || 'gemini-3.5', req.id, req.name, req.frameworkName);
      // Re-fetch request data to refresh UI details
      const updated = this.esgService.getRequestById(req.id);
      this.request.set(updated);
      
      // Reset state
      this.selectedFiles.set([]);
      this.isUploadModalOpen.set(false);
    } catch (err) {
      console.error('Upload failed:', err);
      alert('Failed to upload files. Please try again.');
    } finally {
      this.isUploading.set(false);
    }
  }

  isDeleteDocModalOpen = signal(false);
  docToDelete = signal<string | null>(null);

  onDeleteDocument(filename: string) {
    this.docToDelete.set(filename);
    this.isDeleteDocModalOpen.set(true);
  }

  async confirmDeleteDoc() {
    const filename = this.docToDelete();
    const req = this.request();
    if (req && filename) {
      this.isDeleteDocModalOpen.set(false);
      try {
        await this.esgService.deleteDocument(req.id, filename);
        // Re-fetch request data to refresh UI details
        const updated = this.esgService.getRequestById(req.id);
        this.request.set(updated);
      } catch (err) {
        console.error('Failed to delete document:', err);
      } finally {
        this.docToDelete.set(null);
      }
    }
  }

  // Document viewer modal states & controls
  isViewDocModalOpen = signal(false);
  viewDocumentUrl = signal<SafeResourceUrl | null>(null);
  viewDocumentRawUrl = signal<string | null>(null);
  viewDocumentName = signal<string | null>(null);
  viewDocumentFileType = signal<'docx' | 'pdf' | 'text' | 'image' | 'unknown'>('unknown');
  isDocLoading = signal<boolean>(false);
  docLoadError = signal<string | null>(null);
  docTextContent = signal<string | null>(null);
  zoomLevel = signal<number>(100);
  isFullScreen = signal<boolean>(false);

  onViewDocument(filename: string) {
    const req = this.request();
    if (!req) return;

    const rawUrl = `http://localhost:8000/esg/requests/${req.id}/files/${encodeURIComponent(filename)}/view`;
    const ext = filename.split('.').pop()?.toLowerCase() || '';

    this.viewDocumentName.set(filename);
    this.viewDocumentRawUrl.set(rawUrl);
    this.docLoadError.set(null);
    this.docTextContent.set(null);
    this.zoomLevel.set(100);
    this.isFullScreen.set(false);
    this.isDocLoading.set(true);

    if (ext === 'docx' || ext === 'doc') {
      this.viewDocumentFileType.set('docx');
      this.viewDocumentUrl.set(null);
      this.isViewDocModalOpen.set(true);

      fetch(rawUrl)
        .then(res => {
          if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
          return res.arrayBuffer();
        })
        .then(arrayBuffer => {
          this.isDocLoading.set(false);
          setTimeout(() => {
            const container = document.getElementById('docx-render-container');
            if (container) {
              container.innerHTML = '';
              import('docx-preview').then(docxModule => {
                docxModule.renderAsync(arrayBuffer, container, undefined, {
                  className: 'docx-preview-style',
                  inWrapper: true,
                  ignoreWidth: false,
                  ignoreHeight: false,
                  breakPages: true,
                  ignoreLastRenderedPageBreak: true
                }).catch(err => {
                  console.error('Error rendering docx:', err);
                  this.docLoadError.set('Could not render document formatting cleanly.');
                });
              }).catch(err => {
                console.error('Failed to load docx-preview package:', err);
                this.docLoadError.set('Document preview engine failed to initialize.');
              });
            }
          }, 80);
        })
        .catch(err => {
          console.error('Error fetching docx file:', err);
          this.isDocLoading.set(false);
          this.docLoadError.set('Failed to load document file from server.');
        });
    } else if (ext === 'pdf') {
      this.viewDocumentFileType.set('pdf');
      this.viewDocumentUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(rawUrl));
      this.isDocLoading.set(false);
      this.isViewDocModalOpen.set(true);
    } else if (['txt', 'csv', 'log', 'json', 'xml', 'md'].includes(ext)) {
      this.viewDocumentFileType.set('text');
      this.viewDocumentUrl.set(null);
      this.isViewDocModalOpen.set(true);

      fetch(rawUrl)
        .then(res => {
          if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
          return res.text();
        })
        .then(text => {
          this.docTextContent.set(text);
          this.isDocLoading.set(false);
        })
        .catch(err => {
          console.error('Error fetching text file:', err);
          this.isDocLoading.set(false);
          this.docLoadError.set('Failed to read document text contents.');
        });
    } else if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'svg'].includes(ext)) {
      this.viewDocumentFileType.set('image');
      this.viewDocumentUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(rawUrl));
      this.isDocLoading.set(false);
      this.isViewDocModalOpen.set(true);
    } else {
      this.viewDocumentFileType.set('unknown');
      this.viewDocumentUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(rawUrl));
      this.isDocLoading.set(false);
      this.isViewDocModalOpen.set(true);
    }
  }

  closeViewDocModal() {
    this.isViewDocModalOpen.set(false);
    this.viewDocumentUrl.set(null);
    this.viewDocumentRawUrl.set(null);
    this.viewDocumentName.set(null);
    this.docTextContent.set(null);
    this.docLoadError.set(null);
    this.isDocLoading.set(false);
  }

  zoomIn() {
    this.zoomLevel.update(z => Math.min(z + 20, 200));
  }

  zoomOut() {
    this.zoomLevel.update(z => Math.max(z - 20, 50));
  }

  resetZoom() {
    this.zoomLevel.set(100);
  }

  toggleFullScreen() {
    this.isFullScreen.update(f => !f);
  }

  printDocument() {
    const rawUrl = this.viewDocumentRawUrl();
    if (!rawUrl) return;
    if (this.viewDocumentFileType() === 'pdf') {
      const printWin = window.open(rawUrl, '_blank');
      printWin?.print();
    } else if (this.viewDocumentFileType() === 'docx') {
      const container = document.getElementById('docx-render-container');
      if (container) {
        const printWin = window.open('', '_blank');
        if (printWin) {
          printWin.document.write(`
            <!DOCTYPE html>
            <html>
              <head>
                <title>${this.viewDocumentName() || 'Document'}</title>
                <style>
                  body { margin: 20px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
                  .docx-wrapper { padding: 0; background: none; }
                  .docx { box-shadow: none !important; border: none !important; margin: 0 !important; }
                </style>
              </head>
              <body>${container.innerHTML}</body>
            </html>
          `);
          printWin.document.close();
          printWin.focus();
          setTimeout(() => { printWin.print(); }, 500);
        }
      }
    } else if (this.viewDocumentFileType() === 'text') {
      const text = this.docTextContent() || '';
      const printWin = window.open('', '_blank');
      if (printWin) {
        printWin.document.write(`
          <!DOCTYPE html>
          <html>
            <head><title>${this.viewDocumentName() || 'Document'}</title></head>
            <body><pre style="font-family: monospace; white-space: pre-wrap; word-break: break-all;">${text}</pre></body>
          </html>
        `);
        printWin.document.close();
        printWin.focus();
        setTimeout(() => { printWin.print(); }, 200);
      }
    } else {
      window.open(rawUrl, '_blank');
    }
  }

  copyTextContent() {
    const text = this.docTextContent();
    if (text) {
      navigator.clipboard.writeText(text);
      this.showNotification('Document text copied to clipboard', 'success');
    }
  }


  notification = signal<{ message: string; type: 'success' | 'error' } | null>(null);

  showNotification(message: string, type: 'success' | 'error' = 'error') {
    this.notification.set({ message, type });
    setTimeout(() => {
      this.notification.set(null);
    }, 6000);
  }

  isGenerating = signal(false);
  isDownloadingPdf = signal(false);

  generationStep = signal<number>(0);
  generationProgressText = computed(() => {
    switch (this.generationStep()) {
      case 0: return 'Initializing RAG pipeline & parsing questionnaire module...';
      case 1: return 'Searching ingested documents for disclosures...';
      case 2: return 'Analyzing ESG metrics & generating compliance answers...';
      case 3: return 'Calculating confidence scores & citations...';
      case 4: return 'Formatting report layout & compiling professional PDF...';
      case 5: return 'Saving generated version & finalizing status...';
      default: return 'Processing...';
    }
  });

  isModuleModalOpen = signal(false);
  selectedModule = signal<'basic' | 'comprehensive'>('basic');

  isChangeModelModalOpen = signal(false);
  pendingNewModel = signal<string>('gemini-3.5');

  onModelEngineChange(event: any) {
    const newModel = event.target.value;
    const req = this.request();
    if (!req) return;

    // Immediately revert the UI selection until they confirm the switch
    event.target.value = req.model || 'gemini-3.5';

    // Show custom modal
    this.pendingNewModel.set(newModel);
    this.isChangeModelModalOpen.set(true);
  }

  async confirmModelChangeSubmit() {
    this.isChangeModelModalOpen.set(false);
    const req = this.request();
    const newModel = this.pendingNewModel();
    if (!req || !newModel) return;

    try {
      await this.esgService.updateRequestModel(req.id, newModel);
      // Refresh request state
      const updated = this.esgService.getRequestById(req.id);
      if (updated) {
        this.request.set(updated);
      }
      this.showNotification('Model updated. Rebuilding vector index in the background...', 'success');
    } catch (err) {
      console.error('Failed to update request model:', err);
      this.showNotification('Failed to change analysis model configuration. State not updated.', 'error');
      
      // Explicitly revert the select element value in case Angular change detection needs a fallback
      const selectElement = document.querySelector('select') as HTMLSelectElement;
      if (selectElement) {
        selectElement.value = req.model || 'gemini-3.5';
      }
    }
  }

  onGenerateReport() {
    this.isModuleModalOpen.set(true);
  }

  onGenerateReportSubmit() {
    const req = this.request();
    if (!req) return;
    
    this.isModuleModalOpen.set(false);
    this.isGenerating.set(true);
    this.generationStep.set(0);

    // Smooth scroll down to the processing container once rendered
    setTimeout(() => {
      const element = document.getElementById('processingSection');
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 100);

    const model = req.model || 'gemini-3.5';
    const url = `http://localhost:8000/esg/report/generate/stream?requestId=${req.id}&module=${this.selectedModule()}&model=${model}`;
    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.error) {
          eventSource.close();
          this.isGenerating.set(false);
          this.showNotification(`Failed to generate ESG report: ${data.text || 'Server error.'}`, 'error');
          return;
        }

        if (data.completed) {
          eventSource.close();
          
          // Reload all requests first to refresh the list state
          this.esgService.loadRequests().then(() => {
            const updated = this.esgService.getRequestById(req.id);
            this.request.set(updated);
            this.isGenerating.set(false);
            this.loadNormalizedJson();
            
            if (data.pdf_generated === false) {
              this.showNotification('Workforce metrics generated, but PDF report compilation failed on the backend.', 'error');
            } else {
              this.showNotification('ESG report generated and PDF compiled successfully.', 'success');
            }
          });
          return;
        }

        if (typeof data.step === 'number') {
          this.generationStep.set(data.step);
        }
      } catch (err) {
        console.error('Failed to parse SSE event:', err);
      }
    };

    eventSource.onerror = (err) => {
      console.error('EventSource connection error:', err);
      eventSource.close();
      this.isGenerating.set(false);
      this.showNotification('Failed to generate ESG report. Please check if the LLM backend is responsive.', 'error');
    };
  }
  isDownloadModalOpen = signal(false);
  selectedDownloadVersion = signal<string>('');

  formatReportVersionName(filename: string): string {
    if (!filename) return '';
    // Expected format: esg_report-v{version}-{module}.pdf or esg_report-v{version}.pdf
    const match = filename.match(/-v(\d+)(?:-([\w-]+))?\.pdf$/);
    if (match) {
      const version = match[1];
      const module = match[2];
      if (module) {
        // Capitalize first letter of module
        const capitalizedModule = module.charAt(0).toUpperCase() + module.slice(1);
        return `Version ${version} (${capitalizedModule})`;
      }
      return `Version ${version}`;
    }
    return filename;
  }

  isDocsExpanded = signal(false);
  visibleDocs = computed(() => {
    const req = this.request();
    if (!req || !req.docs) return [];
    if (this.isDocsExpanded() || req.docs.length <= 3) {
      return req.docs;
    }
    return req.docs.slice(0, 3);
  });

  getMalePercentage() {
    const json = this.normalizedReportJson();
    if (!json || !json.social || !json.social.employees) return 50;
    const maleVal = parseFloat(json.social.employees.male);
    const femaleVal = parseFloat(json.social.employees.female);
    if (isNaN(maleVal) && isNaN(femaleVal)) return 50;
    const total = (isNaN(maleVal) ? 0 : maleVal) + (isNaN(femaleVal) ? 0 : femaleVal);
    if (total === 0) return 50;
    return Math.round((isNaN(maleVal) ? 0 : maleVal) / total * 100);
  }

  getFemalePercentage() {
    const json = this.normalizedReportJson();
    if (!json || !json.social || !json.social.employees) return 50;
    const maleVal = parseFloat(json.social.employees.male);
    const femaleVal = parseFloat(json.social.employees.female);
    if (isNaN(maleVal) && isNaN(femaleVal)) return 50;
    const total = (isNaN(maleVal) ? 0 : maleVal) + (isNaN(femaleVal) ? 0 : femaleVal);
    if (total === 0) return 50;
    return Math.round((isNaN(femaleVal) ? 0 : femaleVal) / total * 100);
  }

  getPermPercentage() {
    const json = this.normalizedReportJson();
    if (!json || !json.social || !json.social.employees) return 100;
    const permVal = parseFloat(json.social.employees.permanent);
    const tempVal = parseFloat(json.social.employees.temporary);
    if (isNaN(permVal) && isNaN(tempVal)) return 100;
    const total = (isNaN(permVal) ? 0 : permVal) + (isNaN(tempVal) ? 0 : tempVal);
    if (total === 0) return 100;
    return Math.round((isNaN(permVal) ? 0 : permVal) / total * 100);
  }

  getTempPercentage() {
    const json = this.normalizedReportJson();
    if (!json || !json.social || !json.social.employees) return 0;
    const permVal = parseFloat(json.social.employees.permanent);
    const tempVal = parseFloat(json.social.employees.temporary);
    if (isNaN(permVal) && isNaN(tempVal)) return 0;
    const total = (isNaN(permVal) ? 0 : permVal) + (isNaN(tempVal) ? 0 : tempVal);
    if (total === 0) return 0;
    return Math.round((isNaN(tempVal) ? 0 : tempVal) / total * 100);
  }

  getTotalEmissions() {
    const json = this.normalizedReportJson();
    if (!json || !json.environment) return 0;
    const s1 = parseFloat(json.environment.scope1?.value) || 0;
    const s2 = parseFloat(json.environment.scope2?.value) || 0;
    const s3 = parseFloat(json.environment.scope3?.value) || 0;
    return s1 + s2 + s3;
  }

  getScopePercentage(scopeNum: 1 | 2 | 3) {
    const total = this.getTotalEmissions();
    if (total === 0) return 33;
    const json = this.normalizedReportJson();
    if (!json || !json.environment) return 33;
    const scopeData = json.environment[`scope${scopeNum}`];
    const val = parseFloat(scopeData?.value) || 0;
    return Math.round((val / total) * 100);
  }

  formatConsumption(val: any): string {
    if (val === null || val === undefined || val === 'null' || val === '') {
      return 'Not Disclosed';
    }
    const num = parseFloat(val);
    if (isNaN(num)) {
      return val.toString();
    }
    return num.toLocaleString();
  }

  getMonthlyElectricityData() {
    const json = this.normalizedReportJson();
    return json?.environment?.electricity?.monthlyElectricityConsumption || [];
  }

  getMaxMonthlyElectricity(): number {
    const list = this.getMonthlyElectricityData();
    if (!list.length) return 100000;
    const max = Math.max(...list.map((item: any) => parseFloat(item.consumption) || 0));
    return max > 0 ? max : 100000;
  }

  getElectricityBarHeight(val: any): number {
    const num = parseFloat(val) || 0;
    const max = this.getMaxMonthlyElectricity();
    return Math.round((num / max) * 100);
  }

  getCleanElectricityKwh(consumption: any, percentage: any): number {
    const c = parseFloat(consumption) || 0;
    const p = parseFloat(percentage) || 0;
    return Math.round((c * p) / 100);
  }

  getMonthlyWaterData() {
    const json = this.normalizedReportJson();
    return json?.environment?.water?.monthlyWaterConsumption || [];
  }

  getMaxMonthlyWater(): number {
    const list = this.getMonthlyWaterData();
    if (!list.length) return 1000;
    const max = Math.max(...list.map((item: any) => Math.max(
      parseFloat(item.withdrawn) || 0,
      parseFloat(item.consumption) || 0,
      parseFloat(item.recycled) || 0,
      parseFloat(item.discharged) || 0
    )));
    return max > 0 ? max : 1000;
  }

  getWaterBarHeight(val: any): number {
    const num = parseFloat(val) || 0;
    const max = this.getMaxMonthlyWater();
    return Math.round((num / max) * 100);
  }

  getIncidentsCount(): number {
    const json = this.normalizedReportJson();
    if (!json || !json.social) return 0;
    const val = json.social.incidents;
    if (val === undefined || val === null || val === '') return 0;
    const parsed = parseInt(val, 10);
    return isNaN(parsed) ? 0 : parsed;
  }

  onDownloadReportClick() {
    const req = this.request();
    if (!req) return;
    
    if (req.generatedReports && req.generatedReports.length > 0) {
      this.selectedDownloadVersion.set(req.generatedReports[0]);
      this.isDownloadModalOpen.set(true);
    } else {
      this.onDownloadReport();
    }
  }

  onDownloadReportSubmit() {
    this.isDownloadModalOpen.set(false);
    this.onDownloadReport(this.selectedDownloadVersion());
  }
  async onDownloadReport(filename?: string) {
    const req = this.request();
    if (!req) return;

    this.isDownloadingPdf.set(true);
    try {
      const blob = await this.esgService.downloadReportBlob(req.id, filename);
      
      let downloadName = `ESG_Report_${req.id}.pdf`;
      if (filename) {
        const match = filename.match(/-v\d+\.pdf$/);
        if (match) {
          downloadName = `ESG_Report_${req.id}${match[0]}`;
        }
      }
      
      // Create local URL and trigger download
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = downloadName;
      link.click();
      
      window.URL.revokeObjectURL(url);
      this.showNotification('PDF Report downloaded successfully.', 'success');
    } catch (err: any) {
      console.error('Failed to download PDF report:', err);
      if (err instanceof HttpErrorResponse) {
        if (err.status === 404) {
          this.showNotification('No ESG report has been generated yet. Please click "Generate ESG Report" first.', 'error');
        } else if (err.error instanceof Blob) {
          const reader = new FileReader();
          reader.onload = () => {
            try {
              const errObj = JSON.parse(reader.result as string);
              this.showNotification(`Failed to download report: ${errObj.detail || 'Server error.'}`, 'error');
            } catch (e) {
              this.showNotification('Failed to download PDF report. Server returned an error.', 'error');
            }
          };
          reader.readAsText(err.error);
        } else {
          this.showNotification(`Failed to download report: ${err.error?.detail || 'Server error.'}`, 'error');
        }
      } else {
        this.showNotification('Failed to download PDF report. The document might not be ready or compiled.', 'error');
      }
    } finally {
      this.isDownloadingPdf.set(false);
    }
  }
}
