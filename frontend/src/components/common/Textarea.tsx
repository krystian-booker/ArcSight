/**
 * Textarea component with label and error support
 */

import { forwardRef } from 'react';
import type { TextareaHTMLAttributes } from 'react';

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, helperText, className = '', ...props }, ref) => {
    const textareaId = props.id || `textarea-${Math.random().toString(36).substr(2, 9)}`;

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={textareaId}
            className="mb-2xs block text-[0.85rem] font-medium uppercase tracking-arc-tight text-arc-accent"
          >
            {label}
            {props.required && <span className="ml-1 text-arc-danger">*</span>}
          </label>
        )}
        <textarea
          ref={ref}
          id={textareaId}
          className={`
            w-full rounded-arc-sm form-control-bg px-[0.9rem] py-[0.7rem]
            text-arc-text placeholder-arc-subtle
            transition-all duration-arc ease-arc-out
            focus:outline-none focus:border-arc-teal/60 focus:shadow-[0_0_0_2px_rgba(0,194,168,0.25)]
            disabled:cursor-not-allowed disabled:opacity-50
            resize-y
            ${error ? 'border-arc-danger' : 'hover:border-white/8'}
            ${className}
          `}
          {...props}
        />
        {error && <p className="mt-2xs text-sm text-arc-danger">{error}</p>}
        {helperText && !error && (
          <p className="mt-2xs text-sm text-arc-subtle">{helperText}</p>
        )}
      </div>
    );
  }
);

Textarea.displayName = 'Textarea';

export default Textarea;
