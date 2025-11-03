/**
 * Axios API client with interceptors and error handling
 */

import axios from 'axios';
import type { AxiosError, AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import type { ApiError } from '@/types';

/**
 * Create and configure Axios instance
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 30000, // 30 second timeout
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Request interceptor
 * Add any auth tokens, request timing, etc.
 */
apiClient.interceptors.request.use(
  (config) => {
    // Add request timestamp for latency tracking
    config.headers['X-Request-Time'] = Date.now().toString();
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * Response interceptor
 * Handle errors globally and log response times
 */
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    // Calculate request latency
    const requestTime = response.config.headers['X-Request-Time'];
    if (requestTime) {
      const latency = Date.now() - parseInt(requestTime as string, 10);
      if (latency > 1000) {
        console.warn(`Slow API request: ${response.config.url} took ${latency}ms`);
      }
    }
    return response;
  },
  (error: AxiosError) => {
    // Transform error into ApiError format
    const apiError: ApiError = {
      message: error.message || 'An unexpected error occurred',
      status: error.response?.status,
      code: error.code,
    };

    // Extract error message from response if available
    if (error.response?.data) {
      const data = error.response.data as any;
      if (data.error) {
        apiError.message = data.error;
      } else if (data.message) {
        apiError.message = data.message;
      }
    }

    // Log errors for debugging
    console.error('API Error:', {
      url: error.config?.url,
      method: error.config?.method,
      status: apiError.status,
      message: apiError.message,
    });

    return Promise.reject(apiError);
  }
);

/**
 * Generic GET request
 */
export async function get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const response = await apiClient.get<T>(url, config);
  return response.data;
}

/**
 * Generic POST request
 */
export async function post<T>(
  url: string,
  data?: any,
  config?: AxiosRequestConfig
): Promise<T> {
  const response = await apiClient.post<T>(url, data, config);
  return response.data;
}

/**
 * Generic PUT request
 */
export async function put<T>(
  url: string,
  data?: any,
  config?: AxiosRequestConfig
): Promise<T> {
  const response = await apiClient.put<T>(url, data, config);
  return response.data;
}

/**
 * Generic DELETE request
 */
export async function del<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
  const response = await apiClient.delete<T>(url, config);
  return response.data;
}

/**
 * Upload file with FormData
 */
export async function uploadFile<T>(
  url: string,
  formData: FormData,
  onUploadProgress?: (progressEvent: any) => void
): Promise<T> {
  const response = await apiClient.post<T>(url, formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    onUploadProgress,
  });
  return response.data;
}

/**
 * Download file as blob
 */
export async function downloadFile(url: string, filename?: string): Promise<void> {
  const response = await apiClient.get(url, {
    responseType: 'blob',
  });

  // Create blob link to download
  const blob = new Blob([response.data]);
  const link = document.createElement('a');
  link.href = window.URL.createObjectURL(blob);
  link.download = filename || 'download';
  link.click();
  window.URL.revokeObjectURL(link.href);
}

export default apiClient;
