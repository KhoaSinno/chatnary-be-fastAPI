#!/bin/bash
# Phase 1 Evaluation Script
echo "=== PHASE 1 EVALUATION ==="

mkdir -p test_results/phase1

echo "📊 Testing Phase 1 Implementation..."

# Test 1: Basic functionality
echo "Test 1: Basic RAG functionality"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"DBMS là gì?","k_vector":30,"k_keyword":20,"rerank_top_n":5}' \
  > test_results/phase1/basic_test.json

# Check if citations exist
citations=$(grep -o '\[' test_results/phase1/basic_test.json | wc -l)
sources=$(grep -o '"document_id"' test_results/phase1/basic_test.json | wc -l)
echo "  Citations found: $citations"
echo "  Sources found: $sources"

if [ $citations -gt 2 ] && [ $sources -gt 3 ]; then
  echo "  ✅ Basic test PASSED"
else
  echo "  ❌ Basic test FAILED"
fi

# Test 2: RRF and Locality Penalty
echo -e "\nTest 2: RRF Fusion & Locality Penalty"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Hệ quản trị cơ sở dữ liệu có những thành phần và chức năng gì?","k_vector":40,"k_keyword":25,"rerank_top_n":6}' \
  > test_results/phase1/rrf_test.json

# Check source diversity (different chunk indices)
chunk_indices=$(grep -o '"chunk_index":[0-9]*' test_results/phase1/rrf_test.json | sort -u | wc -l)
echo "  Unique chunk indices: $chunk_indices"

if [ $chunk_indices -gt 4 ]; then
  echo "  ✅ RRF & Locality Penalty working (diverse sources)"
else
  echo "  ⚠️  May need adjustment (sources too clustered)"
fi

# Test 3: Complex Vietnamese Query
echo -e "\nTest 3: Vietnamese text processing"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Quản trị viên cơ sở dữ liệu có trách nhiệm gì?","k_vector":35,"k_keyword":20,"rerank_top_n":5}' \
  > test_results/phase1/vietnamese_test.json

vietnamese_sources=$(grep -o '"document_id"' test_results/phase1/vietnamese_test.json | wc -l)
echo "  Vietnamese query sources: $vietnamese_sources"

if [ $vietnamese_sources -gt 2 ]; then
  echo "  ✅ Vietnamese processing PASSED"
else
  echo "  ❌ Vietnamese processing FAILED"
fi

# Test 4: List Query Performance
echo -e "\nTest 4: List query capability"
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Liệt kê các học phần chuyên ngành","k_vector":60,"k_keyword":40,"rerank_top_n":8}' \
  > test_results/phase1/list_test.json

list_items=$(grep -o '[0-9]\.' test_results/phase1/list_test.json | wc -l)
echo "  List items found: $list_items"

if [ $list_items -gt 5 ]; then
  echo "  ✅ List queries working (Phase 2 may enhance further)"
else
  echo "  ⚠️  List queries need Phase 2 implementation"
fi

# Test 5: Performance measurement
echo -e "\nTest 5: Performance measurement (5 runs)"
total_time=0
success_count=0

for i in {1..5}; do
  echo -n "  Run $i: "
  
  start_time=$(date +%s%3N)
  result=$(curl -s -X POST http://localhost:8000/ask \
    -H "Content-Type: application/json" \
    -d '{"query":"Database management system architecture","k_vector":40,"rerank_top_n":6}')
  end_time=$(date +%s%3N)
  
  elapsed=$((end_time - start_time))
  echo "${elapsed}ms"
  
  # Check if successful
  if echo "$result" | grep -q '"answer"'; then
    success_count=$((success_count + 1))
    total_time=$((total_time + elapsed))
  fi
  
  sleep 1
done

if [ $success_count -gt 0 ]; then
  avg_time=$((total_time / success_count))
  echo "  Average response time: ${avg_time}ms"
  echo "  Success rate: $success_count/5"
  
  if [ $avg_time -lt 4000 ]; then
    echo "  ✅ Performance target met (<4s)"
  else
    echo "  ⚠️  Performance needs optimization (${avg_time}ms >= 4000ms)"
  fi
else
  echo "  ❌ All performance tests failed"
fi

# Generate summary report
echo -e "\n📋 PHASE 1 EVALUATION SUMMARY"
echo "=============================="

# Count total tests
total_tests=5
passed_tests=0

# Basic functionality
if [ $citations -gt 2 ] && [ $sources -gt 3 ]; then
  passed_tests=$((passed_tests + 1))
fi

# RRF & Locality
if [ $chunk_indices -gt 4 ]; then
  passed_tests=$((passed_tests + 1))
fi

# Vietnamese
if [ $vietnamese_sources -gt 2 ]; then
  passed_tests=$((passed_tests + 1))
fi

# List queries
if [ $list_items -gt 5 ]; then
  passed_tests=$((passed_tests + 1))
fi

# Performance
if [ $success_count -gt 0 ] && [ $avg_time -lt 4000 ]; then
  passed_tests=$((passed_tests + 1))
fi

echo "✅ Tests passed: $passed_tests/$total_tests"

# Detailed metrics
echo -e "\n📊 Key Metrics:"
echo "  • Citations implemented: $citations inline citations"
echo "  • Source diversity: $chunk_indices unique chunks" 
echo "  • Vietnamese support: $vietnamese_sources sources"
echo "  • List capability: $list_items items detected"
echo "  • Average latency: ${avg_time}ms"
echo "  • Success rate: $success_count/5 queries"

# Recommendations
echo -e "\n🎯 Recommendations:"
if [ $passed_tests -ge 4 ]; then
  echo "  ✅ Phase 1 implementation is SUCCESSFUL!"
  echo "  ✅ Ready to proceed to Phase 2 (List-Mode & Query Intelligence)"
  echo "  ✅ Core RRF fusion and citations working well"
else
  echo "  ⚠️  Phase 1 needs fixes before proceeding:"
  
  if [ $citations -le 2 ]; then
    echo "    - Fix citation implementation in LLM generation"
  fi
  
  if [ $chunk_indices -le 4 ]; then
    echo "    - Adjust RRF or locality penalty parameters"
  fi
  
  if [ $vietnamese_sources -le 2 ]; then
    echo "    - Check Vietnamese FTS configuration"
  fi
  
  if [ $avg_time -ge 4000 ]; then
    echo "    - Optimize query performance"
  fi
fi

echo -e "\n📄 Detailed results saved to test_results/phase1/"
echo "=== EVALUATION COMPLETE ==="