import { Injectable, signal, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

export interface EsgRequest {
  id: string;
  year: number;
  status: string;
  numDocs: number;
  docs: { name: string; size: string }[];
  dateUploaded: string;
  reportData?: any;
  generatedReports?: string[];
  model?: string;
  name?: string;
  frameworkName?: string;
}

export interface FrameworkDocument {
  docId: string;
  frameworkName: string;
  description?: string;
  fileName: string;
  fileSize: string;
  uploadedAt: string;
}

@Injectable({
  providedIn: 'root'
})
export class EsgService {
  private http = inject(HttpClient);

  // Hostname for API calls
  readonly hostname = 'http://localhost:8000';
  // readonly hostname = 'https://esg-backend-457991646639.asia-south1.run.app';

  // Default list of requests
  private requestsList = signal<EsgRequest[]>([]);

  constructor() {
    this.loadRequests();
  }

  async loadRequests() {
    try {
      const data = await firstValueFrom(
        this.http.get<EsgRequest[]>(`${this.hostname}/esg/requests`)
      );
      this.requestsList.set(data || []);
    } catch (error) {
      console.warn('Failed to load requests from backend:', error);
      this.requestsList.set([]);
    }
  }

  getRequests() {
    return this.requestsList.asReadonly();
  }

  getRequestById(id: string) {
    return this.requestsList().find(r => r.id === id);
  }

  async uploadDocuments(
    year: number,
    files: File[],
    model: string = 'gemini-3.5',
    requestId?: string,
    name?: string,
    frameworkName: string = 'VSME (Voluntary Sustainability Reporting Standard for SMEs)'
  ): Promise<any> {
    const activeRequestId = requestId || `req_${Date.now()}`;
    const formData = new FormData();
    formData.append('requestId', activeRequestId);
    formData.append('year', year.toString());
    formData.append('model', model);
    if (name) {
      formData.append('name', name);
    }
    if (frameworkName) {
      formData.append('frameworkName', frameworkName);
    }
    files.forEach((file) => {
      formData.append('files', file, file.name);
    });

    // Make the real HTTP POST request to /esg/upload
    let response: any = null;
    try {
      response = await firstValueFrom(
        this.http.post(`${this.hostname}/esg/upload`, formData)
      );
      // Reload list from backend on success
      await this.loadRequests();
      return response;
    } catch (error) {
      console.warn('API call failed or not found, falling back to local state update:', error);
      
      // Fallback local update if API fails
      if (requestId) {
        // Appending to existing request in mock local state
        this.requestsList.update(list => list.map(r => {
          if (r.id === requestId) {
            const newDocs = [...r.docs, ...files.map(f => ({
              name: f.name,
              size: `${(f.size / (1024 * 1024)).toFixed(1)} MB`
            }))];
            return {
              ...r,
              numDocs: newDocs.length,
              docs: newDocs,
              status: 'Pending Review'
            };
          }
          return r;
        }));
      } else {
        // Creating new request in mock local state
        const newRequest: EsgRequest = {
          id: activeRequestId,
          year: year,
          status: 'Pending Review',
          numDocs: files.length,
          docs: files.map(f => ({
            name: f.name,
            size: `${(f.size / (1024 * 1024)).toFixed(1)} MB`
          })),
          dateUploaded: new Date().toLocaleDateString('en-US', {
            month: 'short',
            day: '2-digit',
            year: 'numeric'
          }),
          model: model,
          name: name || ''
        };
        this.requestsList.update(list => [newRequest, ...list]);
      }
      return response || { status: 'SUCCESS' };
    }
  }

  async deleteRequest(id: string): Promise<any> {
    let response: any = null;
    try {
      response = await firstValueFrom(
        this.http.delete(`${this.hostname}/esg/requests/${id}`)
      );
      await this.loadRequests();
    } catch (error) {
      console.warn('API call failed or not found, falling back to local state deletion:', error);
      this.requestsList.update(list => list.filter(r => r.id !== id));
    }
    return response || { status: 'SUCCESS' };
  }

  async deleteDocument(requestId: string, filename: string): Promise<any> {
    let response: any = null;
    try {
      response = await firstValueFrom(
        this.http.delete(`${this.hostname}/esg/requests/${requestId}/files/${filename}`)
      );
      await this.loadRequests();
    } catch (error) {
      console.warn('API call failed or not found, falling back to local state document deletion:', error);
      // Fallback local update
      this.requestsList.update(list => list.map(r => {
        if (r.id === requestId) {
          const newDocs = r.docs.filter(d => d.name !== filename);
          return {
            ...r,
            numDocs: newDocs.length,
            docs: newDocs
          };
        }
        return r;
      }));
    }
    return response || { status: 'SUCCESS' };
  }

  async updateRequestModel(requestId: string, model: string): Promise<any> {
    try {
      const response = await firstValueFrom(
        this.http.put(`${this.hostname}/esg/requests/${requestId}/model?model=${model}`, {})
      );
      await this.loadRequests();
      return response;
    } catch (error) {
      console.error('API call failed to update model:', error);
      throw error;
    }
  }

  async generateReport(requestId: string, module: string = 'basic', model: string = 'llama3'): Promise<any> {
    let response: any = null;
    try {
      response = await firstValueFrom(
        this.http.post(`${this.hostname}/esg/report/generate?requestId=${requestId}&module=${module}&model=${model}`, {})
      );
      await this.loadRequests();
    } catch (error) {
      console.warn('API call failed or not found, falling back to local state update:', error);
      // Fallback local update (do not change status)
      this.requestsList.update(list => list.map(r => {
        if (r.id === requestId) {
          return { ...r };
        }
        return r;
      }));
      throw error;
    }
    return response || { status: 'SUCCESS' };
  }

  downloadReport(requestId: string): void {
    window.open(`${this.hostname}/esg/requests/${requestId}/report/download`, '_blank');
  }

  async downloadReportBlob(requestId: string, filename?: string): Promise<Blob> {
    const url = filename
      ? `${this.hostname}/esg/requests/${requestId}/report/download?filename=${filename}`
      : `${this.hostname}/esg/requests/${requestId}/report/download`;
    return await firstValueFrom(
      this.http.get(url, {
        responseType: 'blob'
      })
    );
  }



  async getQuestionnaires(): Promise<any> {
    return await firstValueFrom(
      this.http.get(`${this.hostname}/esg/questionnaires`)
    );
  }

  async getReportNormalizedJson(requestId: string): Promise<any> {
    return await firstValueFrom(
      this.http.get(`${this.hostname}/esg/requests/${requestId}/report/json`)
    );
  }

  async uploadFrameworkDocument(frameworkName: string, file: File, description?: string): Promise<any> {
    const formData = new FormData();
    formData.append('frameworkName', frameworkName);
    formData.append('file', file, file.name);
    if (description) {
      formData.append('description', description);
    }

    return await firstValueFrom(
      this.http.post(`${this.hostname}/esg/frameworks/upload`, formData)
    );
  }

  async getFrameworkDocuments(): Promise<FrameworkDocument[]> {
    try {
      const data = await firstValueFrom(
        this.http.get<FrameworkDocument[]>(`${this.hostname}/esg/frameworks`)
      );
      return data || [];
    } catch (error) {
      console.warn('Failed to load framework documents:', error);
      return [];
    }
  }

  async deleteFrameworkDocument(docId: string): Promise<any> {
    return await firstValueFrom(
      this.http.delete(`${this.hostname}/esg/frameworks/${docId}`)
    );
  }

  downloadFrameworkDocument(docId: string): void {
    window.open(`${this.hostname}/esg/frameworks/${docId}/download`, '_blank');
  }
}
