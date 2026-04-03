/**
 * Types para modelos LLM disponíveis.
 */

export interface AvailableModel {
  id: string;
  display_name: string;
  provider: 'google_apikey' | 'openrouter' | 'ollama';
  color: string;
  description?: string;
  input_token_limit?: number;
  output_token_limit?: number;
}

export interface GoogleModelInfo {
  name: string;
  display_name: string;
  supported_generation_methods: string[];
}

export interface GoogleModelCheckResponse {
  models: GoogleModelInfo[];
}
