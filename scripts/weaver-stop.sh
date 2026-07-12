#!/bin/bash
# إيقاف WeaverCode في الخلفية
if [ -f ~/.weaver/pids.txt ]; then
    kill $(cat ~/.weaver/pids.txt) 2>/dev/null && echo "🕸️ WeaverCode أُوقف."
    rm -f ~/.weaver/pids.txt
else
    echo "لا توجد عملية عاملة."
fi
