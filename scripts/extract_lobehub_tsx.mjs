// Statically read the small JSX subset used by reviewed LobeHub artwork.
// Never transpile, import or execute an upstream module.
import ts from 'typescript';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import path from 'node:path';

const unwrap = node => {
  while (ts.isParenthesizedExpression(node) || ts.isAsExpression(node) || ts.isSatisfiesExpression(node)) node = node.expression;
  return node;
};
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const hyphenate = key => key.replace(/[A-Z]/g, char => '-'+char.toLowerCase());
const svgAttribute = key => /^(?:viewBox|gradientUnits|gradientTransform|patternUnits|clipPathUnits|maskUnits|filterUnits|stdDeviation|baseFrequency|preserveAspectRatio)$/.test(key) ? key : hyphenate(key);

export function extractArtwork(files, entry, componentName) {
  let nextId = 0, steps = 0;
  const used = new Set(), loading = new Set(), modules = new Map();
  function fail(node, reason = 'Unsupported source expression') {
    throw new Error(`${entry}: ${reason}: ${node?.getText().slice(0, 100)}`);
  }
  function own(object, key, node) {
    if (!object || !Object.hasOwn(object, key) || ['__proto__','prototype','constructor'].includes(String(key))) fail(node, 'Unknown literal property');
    return object[key];
  }
  function evaluate(input, env) {
    if (++steps > 100_000) throw new Error(`${entry}: source complexity limit`);
    const node = unwrap(input);
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
    if (ts.isNumericLiteral(node)) return Number(node.text);
    if (node.kind === ts.SyntaxKind.TrueKeyword) return true;
    if (node.kind === ts.SyntaxKind.FalseKeyword) return false;
    if (node.kind === ts.SyntaxKind.NullKeyword) return null;
    if (ts.isIdentifier(node)) {
      if (!env.has(node.text)) fail(node, 'Unknown identifier');
      return env.get(node.text);
    }
    if (ts.isPrefixUnaryExpression(node) && [ts.SyntaxKind.MinusToken, ts.SyntaxKind.PlusToken].includes(node.operator)) {
      const value = evaluate(node.operand, env);
      if (typeof value !== 'number') fail(node);
      return node.operator === ts.SyntaxKind.MinusToken ? -value : value;
    }
    if (ts.isArrayLiteralExpression(node)) return node.elements.map(element => evaluate(element, env));
    if (ts.isObjectLiteralExpression(node)) {
      const result = Object.create(null);
      for (const prop of node.properties) {
        if (ts.isSpreadAssignment(prop)) {
          // Caller-supplied CSS has no meaning in a standalone source SVG.
          if (!ts.isIdentifier(prop.expression) || prop.expression.text !== 'style') fail(prop, 'Unsupported object spread');
          continue;
        }
        if (!ts.isPropertyAssignment(prop) || (!ts.isIdentifier(prop.name) && !ts.isStringLiteral(prop.name))) fail(prop);
        result[prop.name.text] = evaluate(prop.initializer, env);
      }
      return result;
    }
    if (ts.isPropertyAccessExpression(node)) return own(evaluate(node.expression, env), node.name.text, node);
    if (ts.isElementAccessExpression(node)) return own(evaluate(node.expression, env), evaluate(node.argumentExpression, env), node);
    if (ts.isTemplateExpression(node)) {
      return node.head.text + node.templateSpans.map(span => String(evaluate(span.expression, env))+span.literal.text).join('');
    }
    if (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) return jsx(node, env);
    if (ts.isCallExpression(node)) {
      if (ts.isIdentifier(node.expression) && ['useFillId', 'useFillIds'].includes(node.expression.text)) {
        if (env.get(node.expression.text) !== 'reviewed-fill-hook') fail(node, 'Unrecognised fill hook');
        const values = node.arguments.map(arg => evaluate(arg, env));
        const many = node.expression.text === 'useFillIds';
        const count = many ? values[1] : 1;
        if (typeof values[0] !== 'string' || !Number.isInteger(count) || count < 1 || count > 64 || values.length !== (many ? 2 : 1)) fail(node);
        const ids = Array.from({length: count}, () => {
          const id = `${componentName.toLowerCase()}-${nextId++}`;
          return {id, fill: `url(#${id})`};
        });
        return many ? ids : ids[0];
      }
      if (ts.isPropertyAccessExpression(node.expression) && node.expression.name.text === 'map' && node.arguments.length === 1) {
        const values = evaluate(node.expression.expression, env), fn = unwrap(node.arguments[0]);
        if (!Array.isArray(values) || values.length > 1000 || !ts.isArrowFunction(fn) || fn.parameters.length !== 1 || !ts.isIdentifier(fn.parameters[0].name) || ts.isBlock(fn.body)) fail(node);
        return values.map(value => {
          const local = new Map(env);
          local.set(fn.parameters[0].name.text, value);
          return evaluate(fn.body, local);
        });
      }
    }
    fail(node);
  }
  function bind(name, value, env) {
    if (ts.isIdentifier(name)) { env.set(name.text, value); return; }
    if (ts.isObjectBindingPattern(name) || ts.isArrayBindingPattern(name)) {
      name.elements.forEach((part, index) => {
        if (!ts.isBindingElement(part) || part.dotDotDotToken || part.initializer) fail(part, 'Unsupported binding');
        const key = ts.isArrayBindingPattern(name) ? index : (part.propertyName || part.name).getText();
        bind(part.name, own(value, key, part), env);
      });
      return;
    }
    fail(name);
  }
  function jsx(node, env) {
    const opening = ts.isJsxElement(node) ? node.openingElement : node;
    const tag = opening.tagName.getText();
    if (!/^[a-z][A-Za-z0-9]*$/.test(tag)) fail(node, 'Custom components require reviewed static SVGs');
    const attributes = [];
    for (const prop of opening.attributes.properties) {
      if (ts.isJsxSpreadAttribute(prop)) {
        if (!ts.isIdentifier(prop.expression) || prop.expression.text !== 'rest') fail(prop, 'Unsupported JSX spread');
        continue;
      }
      const key = prop.name.getText();
      if (key === 'key') continue; // React reconciliation metadata, never artwork.
      if (!prop.initializer) fail(prop, 'Boolean SVG attributes are not supported');
      const value = ts.isJsxExpression(prop.initializer) ? evaluate(prop.initializer.expression, env) : prop.initializer.text;
      if (key === 'style') {
        if (!value || typeof value !== 'object' || Array.isArray(value)) fail(prop);
        attributes.push(`style="${escape(Object.entries(value).map(([k,v]) => `${hyphenate(k)}:${v}`).join(';'))}"`);
      } else {
        if (!['string','number'].includes(typeof value) || (typeof value === 'number' && !Number.isFinite(value))) fail(prop);
        attributes.push(`${svgAttribute(key)}="${escape(value)}"`);
      }
    }
    let children = '';
    if (ts.isJsxElement(node)) for (const child of node.children) {
      if (ts.isJsxText(child)) { if (child.text.trim()) children += escape(child.text.trim()); }
      else if (ts.isJsxExpression(child)) {
        if (!child.expression) continue;
        const value = evaluate(child.expression, env);
        function render(value) {
          if (Array.isArray(value)) return value.map(render).join('');
          return value?.svg ?? (value === null || value === false ? '' : escape(value));
        }
        children += render(value);
      } else children += jsx(child, env).svg;
    }
    return {svg: `<${tag}${attributes.length ? ' '+attributes.join(' ') : ''}>${children}</${tag}>`};
  }
  function resolve(from, relative) {
    if (!relative.startsWith('.')) throw new Error(`Unsupported artwork import: ${relative}`);
    const base = path.posix.normalize(path.posix.join(path.posix.dirname(from), relative));
    const candidate = [base, base+'.ts', base+'.tsx'].find(name => Object.hasOwn(files, name));
    if (!candidate || !candidate.startsWith(`src/${componentName}/`)) throw new Error(`Missing/outside artwork source: ${base}`);
    return candidate;
  }
  function readModule(filename) {
    if (modules.has(filename)) return modules.get(filename);
    if (loading.has(filename)) throw new Error(`Cyclic artwork import: ${filename}`);
    if (!Object.hasOwn(files, filename)) throw new Error(`Missing source: ${filename}`);
    loading.add(filename); used.add(filename);
    const source = ts.createSourceFile(filename, files[filename], ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    if (source.parseDiagnostics.length) throw new Error(`Invalid TypeScript: ${filename}`);
    const env = new Map(), components = new Map();
    let defaultName, reexport;
    for (const statement of source.statements) {
      if (ts.isImportDeclaration(statement)) {
        const specifier = statement.moduleSpecifier.text, clause = statement.importClause;
        if (clause?.isTypeOnly) continue;
        if (!clause?.namedBindings || !ts.isNamedImports(clause.namedBindings)) fail(statement, 'Only named artwork imports are supported');
        for (const binding of clause.namedBindings.elements) {
          if (binding.isTypeOnly) continue;
          const imported = (binding.propertyName || binding.name).text;
          if (specifier === 'react' && imported === 'memo') env.set(binding.name.text, 'reviewed-memo');
          else if (specifier === '@/hooks/useFillId' && ['useFillId','useFillIds'].includes(imported) && imported === binding.name.text) env.set(imported, 'reviewed-fill-hook');
          else if (specifier === '../style') env.set(binding.name.text, own(Object.fromEntries(readModule(resolve(filename, specifier)).env), imported, binding));
          else fail(statement, 'Unreviewed artwork import');
        }
      } else if (ts.isVariableStatement(statement)) {
        if (!(statement.declarationList.flags & ts.NodeFlags.Const)) fail(statement, 'Mutable artwork source');
        for (const declaration of statement.declarationList.declarations) {
          const init = unwrap(declaration.initializer);
          if (ts.isCallExpression(init) && ts.isIdentifier(init.expression) && env.get(init.expression.text) === 'reviewed-memo') {
            if (!ts.isIdentifier(declaration.name) || init.arguments.length !== 1 || !ts.isArrowFunction(unwrap(init.arguments[0]))) fail(init);
            components.set(declaration.name.text, unwrap(init.arguments[0]));
          } else bind(declaration.name, evaluate(init, env), env);
        }
      } else if (ts.isExportAssignment(statement)) {
        if (!ts.isIdentifier(statement.expression)) fail(statement);
        defaultName = statement.expression.text;
      } else if (ts.isExportDeclaration(statement)) {
        if (!statement.moduleSpecifier || statement.exportClause?.elements?.length !== 1 || statement.exportClause.elements[0].name.text !== 'default') fail(statement);
        reexport = resolve(filename, statement.moduleSpecifier.text);
      } else if (ts.isExpressionStatement(statement)) {
        const expr = statement.expression;
        if (ts.isStringLiteral(expr)) continue; // 'use client'
        if (ts.isBinaryExpression(expr) && expr.operatorToken.kind === ts.SyntaxKind.EqualsToken && ts.isPropertyAccessExpression(expr.left) && expr.left.name.text === 'displayName' && components.has(expr.left.expression.getText()) && ts.isStringLiteral(expr.right)) continue;
        fail(statement, 'Executable module statements are not supported');
      } else fail(statement);
    }
    const result = {env, components, defaultName, reexport};
    modules.set(filename, result); loading.delete(filename);
    return result;
  }
  function render(filename) {
    const module = readModule(filename);
    if (module.reexport) return render(module.reexport);
    const component = module.components.get(module.defaultName);
    if (!component || component.parameters.length !== 1 || !ts.isObjectBindingPattern(component.parameters[0].name)) throw new Error(`Missing supported default icon: ${filename}`);
    // Only these caller-facing props can be dropped/defaulted for static output.
    for (const prop of component.parameters[0].name.elements) {
      if (!ts.isIdentifier(prop.name) || !['size','style','rest'].includes(prop.name.text) || prop.propertyName) fail(prop, 'Unsupported component parameter');
      if (prop.initializer && (prop.name.text !== 'size' || evaluate(prop.initializer, module.env) !== '1em')) fail(prop);
    }
    const env = new Map(module.env);
    env.set('size', '1em'); env.set('style', Object.create(null)); env.set('rest', Object.create(null));
    let result;
    if (ts.isBlock(component.body)) {
      for (const statement of component.body.statements) {
        if (result !== undefined) fail(statement, 'Statements after return');
        if (ts.isVariableStatement(statement) && statement.declarationList.flags & ts.NodeFlags.Const) {
          for (const declaration of statement.declarationList.declarations) bind(declaration.name, evaluate(declaration.initializer, env), env);
        } else if (ts.isReturnStatement(statement)) result = evaluate(statement.expression, env);
        else fail(statement, 'Executable component statements are not supported');
      }
    } else result = evaluate(component.body, env);
    if (!result?.svg?.startsWith('<svg ')) throw new Error(`Artwork is not an SVG: ${filename}`);
    return result.svg+'\n';
  }
  return {svg: render(entry), sources: [...used].sort()};
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const requests = JSON.parse(readFileSync(0, 'utf8'));
  process.stdout.write(JSON.stringify(requests.map(({files, entry, componentName}) => extractArtwork(files, entry, componentName))));
}
