// mylib2.h
//
// Rewrites of mylib.py in C++.
// TODO: Remove mylib.{h,cc}, and make this the main copy.

#ifndef MYLIB2_H
#define MYLIB2_H

#include "gc_heap.h"

namespace mylib {

class Writer {
 public:
  virtual void write(Str* s) = 0;
  virtual void flush() = 0;
  virtual bool isatty() = 0;
};

class BufWriter : public Writer {
 public:
  BufWriter() : data_(nullptr), len_(0) {
  }
  virtual void write(Str* s) override;
  virtual void flush() override {
  }
  virtual bool isatty() override {
    return false;
  }
  // For cStringIO API
  Str* getvalue() {
    if (data_) {
      Str* ret = gc_heap::NewStr(data_, len_);
      reset();  // Invalidate this instance
      return ret;
    } else {
      // log('') translates to this
      // Strings are immutable so we can do this.
      return gc_heap::kEmptyString;
    }
  }

  // Methods to compile printf format strings to

  // To reuse the global gBuf instance
  // problem: '%r' % obj will recursively call asdl/format.py, which has its
  // own % operations
  void reset() {
    data_ = nullptr;  // make sure we get a new buffer next time
    len_ = 0;
  }

  // Note: we do NOT need to instantiate a Str() to append
  void write_const(const char* s, int len);

  // strategy: snprintf() based on sizeof(int)
  void format_d(int i);
  void format_s(Str* s);
  void format_r(Str* s);  // formats with quotes

  // looks at arbitrary type tags?  Is this possible
  // Passes "this" to functions generated by ASDL?
  void format_r(void* s);

 private:
  // Just like a string, except it's mutable
  char* data_;
  int len_;
};

// Wrap a FILE*
class CFileWriter : public Writer {
 public:
  explicit CFileWriter(FILE* f) : f_(f) {
  }
  virtual void write(Str* s) override;
  virtual void flush() override;
  virtual bool isatty() override;

 private:
  FILE* f_;

  DISALLOW_COPY_AND_ASSIGN(CFileWriter)
};

extern Writer* gStdout;

inline Writer* Stdout() {
  if (gStdout == nullptr) {
    gStdout = new CFileWriter(stdout);
  }
  return gStdout;
}

extern Writer* gStderr;

inline Writer* Stderr() {
  if (gStderr == nullptr) {
    gStderr = new CFileWriter(stderr);
  }
  return gStderr;
}

}  // namespace mylib

// Global formatter
extern mylib::BufWriter gBuf;

#endif  // MYLIB2_H